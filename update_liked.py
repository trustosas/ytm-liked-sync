from ytmusicapi import YTMusic
from datetime import datetime
from requests.exceptions import ReadTimeout
import os


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
        print(f"  Warning: could not update description for {playlist_id}: {e}")


def fetch_playlist_tracks(yt, playlist_id):
    """
    Fetch all tracks from a playlist.
    Returns a list of track dicts (may be empty).
    Raises on hard failure.
    """
    playlist = yt.get_playlist(playlist_id, limit=None)
    return playlist.get('tracks') or []


def sync_playlist(yt, playlist_id, desired_video_ids, custom_desc=None):
    """
    Bring `playlist_id` in line with `desired_video_ids` using surgical add/remove.

    - Removes tracks whose videoId is not in desired_video_ids.
    - Adds videoIds that are not already present.
    - Updates the description regardless.

    `desired_video_ids` should be an ordered list (order is preserved for additions).
    """
    update_description(yt, playlist_id, custom_desc)

    try:
        current_tracks = fetch_playlist_tracks(yt, playlist_id)
    except Exception as e:
        print(f"  Error fetching playlist {playlist_id}: {e}")
        return

    # Build lookup structures
    desired_set = set(desired_video_ids)
    current_by_id = {}
    for track in current_tracks:
        vid = track.get('videoId')
        if vid:
            current_by_id[vid] = track  # last occurrence wins (handles accidental dupes)

    current_set = set(current_by_id.keys())

    to_remove_ids = current_set - desired_set
    to_add_ids    = [vid for vid in desired_video_ids if vid not in current_set]

    print(f"  Current: {len(current_set)} | Desired: {len(desired_set)} | "
          f"To add: {len(to_add_ids)} | To remove: {len(to_remove_ids)}")

    # --- Removals (needs full track objects with setVideoId) ---
    if to_remove_ids:
        tracks_to_remove = [current_by_id[vid] for vid in to_remove_ids]
        print(f"  Removing {len(tracks_to_remove)} track(s)...")
        try:
            yt.remove_playlist_items(playlist_id, tracks_to_remove)
            print("  Removal done.")
        except ReadTimeout:
            print("  Warning: ReadTimeout during removal (YouTube likely processed it anyway).")
        except Exception as e:
            print(f"  Error removing tracks: {e}")

    # --- Additions ---
    if to_add_ids:
        print(f"  Adding {len(to_add_ids)} track(s)...")
        try:
            yt.add_playlist_items(playlist_id, to_add_ids)
            print("  Addition done.")
        except Exception as e:
            print(f"  Error adding tracks: {e}")

    if not to_remove_ids and not to_add_ids:
        print("  Already in sync — no changes needed.")


def sync_from_liked_music(target_playlist_id):
    """Sync target playlist to match Liked Music (LM)."""
    yt = get_yt_client()

    print("Fetching Liked Music tracks...")
    try:
        lm_tracks = fetch_playlist_tracks(yt, 'LM')
    except Exception as e:
        print(f"Error fetching Liked Music: {e}")
        return

    if not lm_tracks:
        print("Liked Music is empty — nothing to sync.")
        return

    print(f"Liked Music: {len(lm_tracks)} track(s)")

    lm_video_ids = [t['videoId'] for t in lm_tracks if t and 'videoId' in t]

    print(f"\nSyncing target playlist ({target_playlist_id})...")
    sync_playlist(yt, target_playlist_id, lm_video_ids,
                  custom_desc="Auto updates with songs I cherish.")

    return lm_tracks  # pass through so separate_playlist can reuse it


def sync_split_playlists(original_playlist_id, audio_playlist_id, video_playlist_id,
                         source_tracks=None):
    """
    Sync audio-only and video-only split playlists from `original_playlist_id`.
    Pass `source_tracks` to skip a redundant fetch if you already have them.
    """
    yt = get_yt_client()

    if source_tracks is None:
        print(f"Fetching source playlist ({original_playlist_id})...")
        try:
            source_tracks = fetch_playlist_tracks(yt, original_playlist_id)
        except Exception as e:
            print(f"Error fetching source playlist: {e}")
            return

    audio_ids = []
    video_ids = []
    for track in source_tracks:
        if not track or 'videoId' not in track:
            continue
        if track.get('videoType') == 'MUSIC_VIDEO_TYPE_ATV':
            audio_ids.append(track['videoId'])
        else:
            video_ids.append(track['videoId'])

    print(f"Split: {len(audio_ids)} audio | {len(video_ids)} video")

    print(f"\nSyncing audio playlist ({audio_playlist_id})...")
    sync_playlist(yt, audio_playlist_id, audio_ids,
                  custom_desc="Playlist containing only audio tracks.")

    print(f"\nSyncing video playlist ({video_playlist_id})...")
    sync_playlist(yt, video_playlist_id, video_ids,
                  custom_desc="Playlist containing only video tracks.")


if __name__ == "__main__":
    TARGET_PLAYLIST_ID = "PLwL1RrduuW2j87j0WKjWG_s_DNc0E_gGk"
    AUDIO_PLAYLIST_ID  = "PLwL1RrduuW2hKfLuMFO7f-Yq8ebyNIQZu"
    VIDEO_PLAYLIST_ID  = "PLwL1RrduuW2jYcJu8E-i0oBajEbxn1k3j"

    print("=" * 60)
    print("Step 1 & 2: Diffing Liked Music → target playlist")
    print("=" * 60)
    lm_tracks = sync_from_liked_music(TARGET_PLAYLIST_ID)

    print("\n" + "=" * 60)
    print("Step 3: Diffing target playlist → audio / video split")
    print("=" * 60)
    # Reuse lm_tracks as the source so we skip a third fetch of the target
    sync_split_playlists(TARGET_PLAYLIST_ID, AUDIO_PLAYLIST_ID, VIDEO_PLAYLIST_ID,
                         source_tracks=lm_tracks)

    print("\n" + "=" * 60)
    print("Process completed successfully!")
    print("=" * 60)
