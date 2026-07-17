"""
update_liked_new.py
Standalone script. Purges and refills a single target playlist with a
1:1 copy of your current Liked Music tracks.
"""

from ytmusicapi import YTMusic
from datetime import datetime
from requests.exceptions import ReadTimeout
import os
import time


def get_yt_client():
    """Dynamically creates browser.json if running in GitHub Actions, else uses local file."""
    if 'YT_BROWSER_JSON' in os.environ:
        with open('browser.json', 'w') as f:
            f.write(os.environ['YT_BROWSER_JSON'])
    return YTMusic('browser.json')


def update_description(yt, playlist_id, custom_desc=None):
    """Update playlist description with current timestamp."""
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M')
    base = custom_desc or "Auto updates with songs I cherish."
    formatted = f"Last updated: {date_str} at {time_str} GMT\n{base}"
    try:
        yt.edit_playlist(playlist_id, description=formatted)
    except Exception as e:
        print(f" Warning: could not update description for {playlist_id}: {e}")


def fetch_playlist_tracks(yt, playlist_id):
    """Fetch all tracks from a playlist. Returns a list of track dicts."""
    playlist = yt.get_playlist(playlist_id, limit=None)
    return playlist.get('tracks') or []


def _do_purge(yt, playlist_id, retry_delay=2):
    """Remove all current tracks from playlist_id and verify it's empty.
    Returns True if confirmed empty, False otherwise. Does not raise on
    a failed verification -- that's left to the caller's cycle retry.
    """
    try:
        current_tracks = fetch_playlist_tracks(yt, playlist_id)
    except Exception as e:
        print(f" Error fetching playlist {playlist_id}: {e}")
        return False

    if not current_tracks:
        print(" Playlist already empty.")
        return True

    print(f" Purging {len(current_tracks)} track(s)...")
    try:
        yt.remove_playlist_items(playlist_id, current_tracks)
        print(" Purge request sent.")
    except ReadTimeout:
        print(" Warning: ReadTimeout during purge (YouTube likely processed it anyway).")
    except Exception as e:
        print(f" Error purging tracks from {playlist_id}: {e}")
        return False

    try:
        remaining = fetch_playlist_tracks(yt, playlist_id)
    except Exception as e:
        print(f" Could not verify purge of {playlist_id} (fetch failed): {e}")
        return False

    if not remaining:
        print(" Purge confirmed empty.")
        return True

    print(f" {len(remaining)} item(s) still present after purge.")
    return False


def _do_refill(yt, playlist_id, video_ids):
    """Add video_ids to playlist_id and verify they're all present.
    Returns True if confirmed complete, False otherwise. Does not raise --
    that's left to the caller's cycle retry.
    """
    if not video_ids:
        print(" No tracks to add.")
        return True

    print(f" Refilling with {len(video_ids)} track(s)...")
    try:
        yt.add_playlist_items(playlist_id, video_ids, duplicates=True)
        print(" Refill request sent.")
    except ReadTimeout:
        print(" Warning: ReadTimeout during refill (YouTube likely processed it anyway).")
    except Exception as e:
        print(f" Error refilling tracks into {playlist_id}: {e}")
        return False

    try:
        current_tracks = fetch_playlist_tracks(yt, playlist_id)
        current_ids = {t['videoId'] for t in current_tracks if t and 'videoId' in t}
    except Exception as e:
        print(f" Could not verify refill of {playlist_id} (fetch failed): {e}")
        return False

    missing_ids = [vid for vid in video_ids if vid not in current_ids]
    if missing_ids:
        print(f" {len(missing_ids)} track(s) still missing after refill.")
        return False

    print(" Refill confirmed complete.")
    return True


def get_playlist_shape(yt, playlist_id):
    """Fetch a playlist once and return its shape, split by videoType:
    - track_count: items where videoType == MUSIC_VIDEO_TYPE_ATV (tracks)
    - video_count: all other items (regular videos)
    - last_video_id: videoId of the last item overall (position-based --
      LM only ever inserts new likes at the top, so the tail is stable
      unless something was unliked)
    - last_track_id: videoId of the last ATV-type item specifically
    """
    playlist = yt.get_playlist(playlist_id, limit=None)
    tracks = playlist.get('tracks') or []

    atv_items = [t for t in tracks if t and t.get('videoType') == 'MUSIC_VIDEO_TYPE_ATV']
    video_items = [t for t in tracks if t and t.get('videoType') != 'MUSIC_VIDEO_TYPE_ATV']

    last_video_id = tracks[-1]['videoId'] if tracks and 'videoId' in tracks[-1] else None
    last_track_id = atv_items[-1]['videoId'] if atv_items and 'videoId' in atv_items[-1] else None

    return {
        'track_count': len(atv_items),
        'video_count': len(video_items),
        'last_video_id': last_video_id,
        'last_track_id': last_track_id,
        'tracks': tracks,
    }


def shapes_match(source_shape, target_shape):
    """Compare two playlist shapes: track counts, video counts, last
    overall videoId, and last track (ATV) videoId must all agree.
    Returns True only if the target is non-empty and everything matches --
    i.e. purge/refill would very likely be wasted effort.
    """
    if source_shape['video_count'] == 0 and source_shape['track_count'] == 0:
        return False

    if target_shape['video_count'] == 0 and target_shape['track_count'] == 0:
        print(" Target is empty -- shape check skipped.")
        return False

    if source_shape['track_count'] != target_shape['track_count']:
        print(f" Shape mismatch: track counts differ "
              f"({source_shape['track_count']} vs {target_shape['track_count']}).")
        return False

    if source_shape['video_count'] != target_shape['video_count']:
        print(f" Shape mismatch: video counts differ "
              f"({source_shape['video_count']} vs {target_shape['video_count']}).")
        return False

    if source_shape['last_video_id'] != target_shape['last_video_id']:
        print(f" Shape mismatch: last video differs "
              f"({source_shape['last_video_id']} vs {target_shape['last_video_id']}).")
        return False

    if source_shape['last_track_id'] != target_shape['last_track_id']:
        print(f" Shape mismatch: last track differs "
              f"({source_shape['last_track_id']} vs {target_shape['last_track_id']}).")
        return False

    print(" Shape check passed: counts and last track/video match. Skipping purge/refill.")
    return True


def purge_and_refill(yt, playlist_id, video_ids, custom_desc=None,
                      max_attempts=5, retry_delay=2):
    """Purge, verify, refill, verify -- as one cycle, retried as a whole.

    If purge verification or refill verification fails, the entire cycle
    (purge -> verify -> refill -> verify) restarts from the top. This
    repeats up to max_attempts times total (not max_attempts per step).

    Raises RuntimeError if the cycle cannot be confirmed successful after
    max_attempts, so the caller/workflow fails loudly.
    """
    for attempt in range(1, max_attempts + 1):
        print(f" Cycle attempt {attempt}/{max_attempts}...")

        if not _do_purge(yt, playlist_id, retry_delay=retry_delay):
            if attempt < max_attempts:
                print(f" Purge/verify failed, retrying whole cycle in {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            raise RuntimeError(
                f"Purge could not be confirmed for playlist {playlist_id} "
                f"after {max_attempts} full cycle attempts."
            )

        if not _do_refill(yt, playlist_id, video_ids):
            if attempt < max_attempts:
                print(f" Refill/verify failed, retrying whole cycle in {retry_delay}s...")
                time.sleep(retry_delay)
                continue
            raise RuntimeError(
                f"Refill could not be confirmed for playlist {playlist_id} "
                f"after {max_attempts} full cycle attempts."
            )

        print(" Cycle confirmed: purge and refill both verified.")
        update_description(yt, playlist_id, custom_desc)
        return


def sync_from_liked_music(target_playlist_id):
    """Purge and refill target playlist from Liked Music. Returns the tracks
    synced, or None if Liked Music is empty or the shape check found the
    target already in sync.
    """
    yt = get_yt_client()

    print("Fetching Liked Music tracks...")
    try:
        lm_shape = get_playlist_shape(yt, 'LM')
    except Exception as e:
        raise RuntimeError(f"Error fetching Liked Music: {e}") from e

    lm_tracks = lm_shape['tracks']
    if not lm_tracks:
        print("Liked Music is empty — nothing to sync.")
        return None

    print(f"Liked Music: {lm_shape['track_count']} track(s), "
          f"{lm_shape['video_count']} regular video(s)")

    print(f"\nChecking shape of target playlist ({target_playlist_id})...")
    try:
        target_shape = get_playlist_shape(yt, target_playlist_id)
    except Exception as e:
        raise RuntimeError(f"Error fetching target playlist {target_playlist_id}: {e}") from e

    if shapes_match(lm_shape, target_shape):
        return None

    lm_video_ids = [t['videoId'] for t in lm_tracks if t and 'videoId' in t]

    print(f"\nSyncing target playlist ({target_playlist_id})...")
    purge_and_refill(yt, target_playlist_id, lm_video_ids,
                      custom_desc="Auto updates with songs I cherish.")
    return lm_tracks


if __name__ == "__main__":
    TARGET_PLAYLIST_ID = "PLwL1RrduuW2g6XKBN5JSugD96tItkPJW4"
    print("=" * 60)
    print("Syncing Liked Music → target playlist")
    print("=" * 60)

    sync_from_liked_music(TARGET_PLAYLIST_ID)

    print("\n" + "=" * 60)
    print("Process completed successfully!")
    print("=" * 60)
