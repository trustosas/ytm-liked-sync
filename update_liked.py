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
    """Fetch all tracks from a playlist. Returns a list of track dicts."""
    playlist = yt.get_playlist(playlist_id, limit=None)
    return playlist.get('tracks') or []


def purge_and_refill(yt, playlist_id, video_ids, custom_desc=None):
    """Empty a playlist then refill it in one batched add."""
    update_description(yt, playlist_id, custom_desc)

    # --- Purge ---
    print(f"  Fetching current tracks...")
    try:
        current_tracks = fetch_playlist_tracks(yt, playlist_id)
    except Exception as e:
        print(f"  Error fetching playlist {playlist_id}: {e}")
        return

    if current_tracks:
        print(f"  Purging {len(current_tracks)} track(s)...")
        try:
            yt.remove_playlist_items(playlist_id, current_tracks)
            print("  Purge done.")
        except ReadTimeout:
            print("  Warning: ReadTimeout during purge (YouTube likely processed it anyway).")
        except Exception as e:
            print(f"  Error purging tracks: {e}")
    else:
        print("  Playlist already empty.")

    # --- Refill ---
    if video_ids:
        print(f"  Refilling with {len(video_ids)} track(s)...")
        try:
            yt.add_playlist_items(playlist_id, video_ids)
            print("  Refill done.")
        except Exception as e:
            print(f"  Error refilling tracks: {e}")
    else:
        print("  No tracks to add.")


def sync_from_liked_music(target_playlist_id):
    """Purge and refill target playlist from Liked Music."""
    yt = get_yt_client()

    print("Fetching Liked Music tracks...")
    try:
        lm_tracks = fetch_playlist_tracks(yt, 'LM')
    except Exception as e:
        print(f"Error fetching Liked Music: {e}")
        return None

    if not lm_tracks:
        print("Liked Music is empty — nothing to sync.")
        return None

    print(f"Liked Music: {len(lm_tracks)} track(s)")

    lm_video_ids = [t['videoId'] for t in lm_tracks if t and 'videoId' in t]

    print(f"\nSyncing target playlist ({target_playlist_id})...")
    purge_and_refill(yt, target_playlist_id, lm_video_ids,
                     custom_desc="Auto updates with songs I cherish.")

    return lm_tracks


def sync_split_playlists(audio_playlist_id, video_playlist_id, source_tracks):
    """Purge and refill audio/video split playlists from source_tracks."""
    yt = get_yt_client()

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
    purge_and_refill(yt, audio_playlist_id, audio_ids,
                     custom_desc="Playlist containing only audio tracks.")

    print(f"\nSyncing video playlist ({video_playlist_id})...")
    purge_and_refill(yt, video_playlist_id, video_ids,
                     custom_desc="Playlist containing only video tracks.")


if __name__ == "__main__":
    TARGET_PLAYLIST_ID = "PLwL1RrduuW2g6XKBN5JSugD96tItkPJW4"
    AUDIO_PLAYLIST_ID  = "PLwL1RrduuW2jC7jwXNca30hHzW3rdPF-E"
    VIDEO_PLAYLIST_ID  = "PLwL1RrduuW2jdBKTAPc88Bl4vKWuU1_T9"

    print("=" * 60)
    print("Step 1 & 2: Syncing Liked Music → target playlist")
    print("=" * 60)
    lm_tracks = sync_from_liked_music(TARGET_PLAYLIST_ID)

    if lm_tracks:
        print("\n" + "=" * 60)
        print("Step 3: Splitting target → audio / video playlists")
        print("=" * 60)
        sync_split_playlists(AUDIO_PLAYLIST_ID, VIDEO_PLAYLIST_ID, lm_tracks)

    print("\n" + "=" * 60)
    print("Process completed successfully!")
    print("=" * 60)
