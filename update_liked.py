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


def empty_playlist(playlist_id, custom_desc=None):
    """Empty all tracks from a playlist and update description"""
    yt = get_yt_client()
    
    # Update description with current timestamp
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M')
    
    if custom_desc:
        formatted = f"Last updated: {date_str} at {time_str}\n{custom_desc}"
    else:
        formatted = f"Last updated: {date_str} at {time_str}\nSemi-automatically updated, with songs I cherish."
        
    try:
        yt.edit_playlist(playlist_id, description=formatted)
        playlist = yt.get_playlist(playlist_id, limit=None)
    except Exception as e:
        print(f"Error fetching/editing playlist {playlist_id}: {e}")
        return

    if 'tracks' not in playlist or len(playlist['tracks']) == 0:
        print(f"Playlist '{playlist['title']}' ({playlist_id}) is already empty.")
        return
    
    print(f"Found {len(playlist['tracks'])} tracks in playlist '{playlist['title']}'")
    
    videos_to_remove = [track for track in playlist['tracks'] if track]
    
    if videos_to_remove:
        print(f"Removing {len(videos_to_remove)} tracks from playlist...")
        try:
            yt.remove_playlist_items(playlist_id, videos_to_remove)
            print("All tracks removed successfully!")
        except ReadTimeout:
            pass
        except Exception as e:
            print(f"Error removing tracks: {e}")
    else:
        print("No valid tracks to remove.")


def copy_tracks_from_liked_music(target_playlist_id):
    """Copy all tracks from Liked Music (LM) to target playlist"""
    yt = get_yt_client()
    
    print("\nFetching Liked Music tracks...")
    liked_music = yt.get_playlist('LM', limit=None)
    
    if 'tracks' not in liked_music or len(liked_music['tracks']) == 0:
        print("No tracks found in Liked Music.")
        return
    
    print(f"Found {len(liked_music['tracks'])} tracks in Liked Music")
    
    video_ids = [track['videoId'] for track in liked_music['tracks'] if track and 'videoId' in track]
    
    if video_ids:
        print(f"Adding {len(video_ids)} tracks to playlist {target_playlist_id}...")
        try:
            yt.add_playlist_items(target_playlist_id, video_ids, duplicates=True)
            print("Tracks added successfully!")
        except Exception as e:
            print(f"Error adding tracks: {e}")
    else:
        print("No valid video IDs to add.")


def separate_playlist(original_playlist_id, audio_playlist_id, video_playlist_id):
    """Separate playlist into audio and video playlists by overwriting existing ones"""
    yt = get_yt_client()
    
    print(f"\nSeparating playlist {original_playlist_id}...")
    original_playlist = yt.get_playlist(original_playlist_id, limit=None)
    print(f"Processing playlist: {original_playlist['title']}")
    
    audio_items = []
    video_items = []
    
    for track in original_playlist['tracks']:
        if track['videoType'] == 'MUSIC_VIDEO_TYPE_ATV':
            audio_items.append(track['videoId'])
        else:
            video_items.append(track['videoId'])
    
    print(f"Audio tracks to add: {len(audio_items)}, Video tracks to add: {len(video_items)}")
    
    # Process Audio Playlist
    print("\n--- Updating Audio Playlist ---")
    empty_playlist(audio_playlist_id, custom_desc="Playlist containing only audio tracks.")
    if audio_items:
        try:
            yt.add_playlist_items(audio_playlist_id, audio_items, duplicates=True)
            print("Audio tracks synced successfully!")
        except Exception as e:
            print(f"Error adding audio tracks: {e}")
            
    # Process Video Playlist
    print("\n--- Updating Video Playlist ---")
    empty_playlist(video_playlist_id, custom_desc="Playlist containing only video tracks.")
    if video_items:
        try:
            yt.add_playlist_items(video_playlist_id, video_items, duplicates=True)
            print("Video tracks synced successfully!")
        except Exception as e:
            print(f"Error adding video tracks: {e}")


if __name__ == "__main__":
    # Your core Target Playlist ID
    TARGET_PLAYLIST_ID = "PLwL1RrduuW2jxAFQpWwO66zM98FsCJb1B"
    
    # TODO: Create these two playlists manually ONCE in your YouTube Music UI, 
    # copy their IDs from the URL bar, and paste them here.
    AUDIO_PLAYLIST_ID = "PLwL1RrduuW2hKfLuMFO7f-Yq8ebyNIQZu"
    VIDEO_PLAYLIST_ID = "PLwL1RrduuW2jYcJu8E-i0oBajEbxn1k3j"
    
    print("=" * 60)
    print("Step 1: Emptying target playlist")
    print("=" * 60)
    empty_playlist(TARGET_PLAYLIST_ID, custom_desc="Semi-automatically updated every Saturday, with songs I cherish.")
    
    print("\n" + "=" * 60)
    print("Step 2: Copying tracks from Liked Music")
    print("=" * 60)
    copy_tracks_from_liked_music(TARGET_PLAYLIST_ID)
    
    print("\n" + "=" * 60)
    print("Step 3: Separating playlist into dedicated audio and video targets")
    print("=" * 60)
    separate_playlist(TARGET_PLAYLIST_ID, AUDIO_PLAYLIST_ID, VIDEO_PLAYLIST_ID)
    
    print("\n" + "=" * 60)
    print("Process completed successfully!")
    print("=" * 60)