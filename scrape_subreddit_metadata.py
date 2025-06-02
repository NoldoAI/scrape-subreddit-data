import praw
from datetime import datetime, UTC
from dotenv import load_dotenv
import pymongo
import os
import time
from rate_limits import check_rate_limit

# Import centralized configuration
from config import DATABASE_NAME, COLLECTIONS, DEFAULT_SCRAPER_CONFIG

load_dotenv()

# MongoDB setup using centralized config
client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
db = client[DATABASE_NAME]
subreddit_collection = db[COLLECTIONS["SUBREDDIT_METADATA"]]

# Reddit API setup
reddit = praw.Reddit(
    client_id=os.getenv("R_CLIENT_ID"),
    client_secret=os.getenv("R_CLIENT_SECRET"),
    username=os.getenv("R_USERNAME"),
    password=os.getenv("R_PASSWORD"),
    user_agent=os.getenv("R_USER_AGENT")
)

# Configuration using centralized values
SUBREDDIT_SCRAPE_INTERVAL = DEFAULT_SCRAPER_CONFIG["subreddit_update_interval"]  # 24 hours between subreddit metadata updates


def scrape_subreddit_metadata(subreddit_name):
    """
    Scrape metadata for a subreddit.
    
    Args:
        subreddit_name (str): Name of the subreddit
    
    Returns:
        dict: Subreddit metadata dictionary
    """
    print(f"\n--- Scraping metadata for r/{subreddit_name} ---")
    
    # Check rate limits before making API calls
    check_rate_limit(reddit)
    
    try:
        subreddit = reddit.subreddit(subreddit_name)
        
        # Collect subreddit metadata
        metadata = {
            "subreddit_name": subreddit_name,
            "display_name": subreddit.display_name,
            "title": subreddit.title,
            "public_description": subreddit.public_description,
            "description": subreddit.description,
            "url": subreddit.url,
            "subscribers": subreddit.subscribers,
            "active_user_count": subreddit.accounts_active,
            "over_18": subreddit.over18,
            "lang": subreddit.lang,
            "created_utc": subreddit.created_utc,
            "created_datetime": datetime.fromtimestamp(subreddit.created_utc),
            "submission_type": subreddit.submission_type,
            "submission_text": subreddit.submit_text,
            "submission_text_label": subreddit.submit_text_label,
            "user_is_moderator": subreddit.user_is_moderator,
            "user_is_subscriber": subreddit.user_is_subscriber,
            "quarantine": subreddit.quarantine,
            "advertiser_category": subreddit.advertiser_category,
            "is_enrolled_in_new_modmail": subreddit.is_enrolled_in_new_modmail,
            "primary_color": subreddit.primary_color,
            "show_media": subreddit.show_media,
            "show_media_preview": subreddit.show_media_preview,
            "spoilers_enabled": subreddit.spoilers_enabled,
            "allow_videos": subreddit.allow_videos,
            "allow_images": subreddit.allow_images,
            "allow_polls": subreddit.allow_polls,
            "allow_discovery": subreddit.allow_discovery,
            "allow_prediction_contributors": subreddit.allow_prediction_contributors,
            "has_menu_widget": subreddit.has_menu_widget,
            "icon_img": subreddit.icon_img,
            "community_icon": subreddit.community_icon,
            "banner_img": subreddit.banner_img,
            "banner_background_image": subreddit.banner_background_image,
            "mobile_banner_image": subreddit.mobile_banner_image,
            "scraped_at": datetime.now(UTC),
            "last_updated": datetime.now(UTC)
        }
        
        print(f"Successfully scraped metadata for r/{subreddit_name}")
        print(f"Subscribers: {metadata['subscribers']:,}")
        print(f"Active users: {metadata['active_user_count']:,}")
        print(f"Created: {metadata['created_datetime'].strftime('%Y-%m-%d')}")
        print(f"Over 18: {metadata['over_18']}")
        print(f"Language: {metadata['lang']}")
        
        return metadata
        
    except Exception as e:
        print(f"Error scraping subreddit metadata: {e}")
        return None


def save_subreddit_metadata(metadata):
    """
    Save subreddit metadata to MongoDB.
    
    Args:
        metadata (dict): Subreddit metadata dictionary
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not metadata:
        return False
    
    try:
        # Create index on subreddit_name for efficient operations
        subreddit_collection.create_index("subreddit_name", unique=True)
        
        # Upsert the metadata (insert if new, update if exists)
        result = subreddit_collection.update_one(
            {"subreddit_name": metadata["subreddit_name"]},
            {"$set": metadata},
            upsert=True
        )
        
        if result.upserted_id:
            print(f"✅ Inserted new subreddit metadata for r/{metadata['subreddit_name']}")
        else:
            print(f"🔄 Updated existing subreddit metadata for r/{metadata['subreddit_name']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving subreddit metadata: {e}")
        return False


def should_update_subreddit_metadata(subreddit_name):
    """
    Check if subreddit metadata should be updated based on last update time.
    
    Args:
        subreddit_name (str): Name of the subreddit
    
    Returns:
        bool: True if should update, False otherwise
    """
    try:
        # Find the most recent metadata for this subreddit
        latest_metadata = subreddit_collection.find_one(
            {"subreddit_name": subreddit_name},
            sort=[("last_updated", -1)]
        )
        
        if not latest_metadata:
            print(f"📋 No existing metadata found for r/{subreddit_name}")
            return True
        
        # Check if enough time has passed since last update
        last_updated = latest_metadata.get("last_updated")
        if not last_updated:
            return True
        
        # Handle both timezone-aware and timezone-naive datetimes
        current_time = datetime.now(UTC)
        if last_updated.tzinfo is None:
            # Database has timezone-naive datetime, convert it to UTC
            last_updated = last_updated.replace(tzinfo=UTC)
        
        time_since_update = (current_time - last_updated).total_seconds()
        should_update = time_since_update >= SUBREDDIT_SCRAPE_INTERVAL
        
        if should_update:
            print(f"⏰ Last subreddit update was {time_since_update/3600:.1f} hours ago - updating")
        else:
            time_until_update = (SUBREDDIT_SCRAPE_INTERVAL - time_since_update) / 3600
            print(f"⏳ Subreddit updated {time_since_update/3600:.1f} hours ago - next update in {time_until_update:.1f} hours")
        
        return should_update
        
    except Exception as e:
        print(f"❌ Error checking subreddit update status: {e}")
        return True  # Default to updating if we can't check


def scrape_and_save_subreddit_metadata(subreddit_name):
    """
    Check if subreddit metadata needs updating and scrape if necessary.
    
    Args:
        subreddit_name (str): Name of the subreddit
    
    Returns:
        bool: True if metadata was updated, False otherwise
    """
    if should_update_subreddit_metadata(subreddit_name):
        metadata = scrape_subreddit_metadata(subreddit_name)
        if metadata:
            return save_subreddit_metadata(metadata)
    return False


def get_subreddit_metadata_stats():
    """
    Get statistics about subreddit metadata collection.
    
    Returns:
        dict: Statistics about subreddit metadata
    """
    try:
        total_subreddits = subreddit_collection.count_documents({})
        
        # Get all subreddits with their last update times
        subreddits = list(subreddit_collection.find(
            {}, 
            {"subreddit_name": 1, "last_updated": 1, "subscribers": 1, "active_user_count": 1}
        ).sort("last_updated", -1))
        
        return {
            "total_subreddits": total_subreddits,
            "subreddits": subreddits
        }
    except Exception as e:
        print(f"❌ Error getting subreddit stats: {e}")
        return {}


def print_subreddit_stats():
    """Print current subreddit metadata statistics."""
    stats = get_subreddit_metadata_stats()
    if stats:
        print(f"\n{'='*60}")
        print("SUBREDDIT METADATA STATISTICS")
        print(f"{'='*60}")
        print(f"Total subreddits tracked: {stats['total_subreddits']}")
        
        if stats['subreddits']:
            print(f"\nRecent subreddit updates:")
            print(f"{'Subreddit':<20} {'Last Updated':<20} {'Subscribers':<12} {'Active':<8}")
            print(f"{'-'*60}")
            
            for sub in stats['subreddits'][:10]:  # Show last 10
                last_updated = sub.get('last_updated', 'Never')
                if isinstance(last_updated, datetime):
                    # Handle both timezone-aware and timezone-naive datetimes
                    current_time = datetime.now(UTC)
                    if last_updated.tzinfo is None:
                        # Database has timezone-naive datetime, convert it to UTC
                        last_updated = last_updated.replace(tzinfo=UTC)
                    time_ago = (current_time - last_updated).total_seconds() / 3600
                    last_updated = f"{time_ago:.1f}h ago"
                
                subscribers = sub.get('subscribers', 0)
                active = sub.get('active_user_count', 0)
                
                print(f"r/{sub['subreddit_name']:<19} {str(last_updated):<20} {subscribers:<12,} {active:<8,}")
        
        print(f"{'='*60}")


def scrape_multiple_subreddits(subreddit_names, force_update=False):
    """
    Scrape metadata for multiple subreddits.
    
    Args:
        subreddit_names (list): List of subreddit names
        force_update (bool): Whether to force update regardless of time interval
    
    Returns:
        dict: Results summary
    """
    print(f"\n🚀 Starting batch subreddit metadata scraping...")
    print(f"📋 Subreddits to process: {len(subreddit_names)}")
    
    results = {
        "total": len(subreddit_names),
        "updated": 0,
        "skipped": 0,
        "errors": 0
    }
    
    for i, subreddit_name in enumerate(subreddit_names, 1):
        print(f"\n📊 Processing {i}/{len(subreddit_names)}: r/{subreddit_name}")
        
        try:
            if force_update or should_update_subreddit_metadata(subreddit_name):
                metadata = scrape_subreddit_metadata(subreddit_name)
                if metadata and save_subreddit_metadata(metadata):
                    results["updated"] += 1
                else:
                    results["errors"] += 1
            else:
                results["skipped"] += 1
            
            # Small delay between subreddits to be respectful
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Error processing r/{subreddit_name}: {e}")
            results["errors"] += 1
    
    print(f"\n{'='*50}")
    print("BATCH SCRAPING SUMMARY")
    print(f"{'='*50}")
    print(f"Total subreddits: {results['total']}")
    print(f"Updated: {results['updated']}")
    print(f"Skipped: {results['skipped']}")
    print(f"Errors: {results['errors']}")
    print(f"{'='*50}")
    
    return results


if __name__ == "__main__":
    import sys
    
    print(f"🔗 Authenticated as: {reddit.user.me()}")
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--stats":
            # Show statistics only
            print_subreddit_stats()
            
        elif command == "--scrape" and len(sys.argv) > 2:
            # Scrape specific subreddit(s)
            subreddits = sys.argv[2].split(',')
            force_update = "--force" in sys.argv
            
            if len(subreddits) == 1:
                # Single subreddit
                subreddit_name = subreddits[0].strip()
                print(f"🎯 Scraping metadata for r/{subreddit_name}...")
                
                if force_update:
                    metadata = scrape_subreddit_metadata(subreddit_name)
                    if metadata:
                        updated = save_subreddit_metadata(metadata)
                        print(f"✅ Force updated r/{subreddit_name}")
                    else:
                        print(f"❌ Failed to scrape r/{subreddit_name}")
                else:
                    updated = scrape_and_save_subreddit_metadata(subreddit_name)
                    print(f"📊 r/{subreddit_name}: {'Updated' if updated else 'No update needed'}")
            else:
                # Multiple subreddits
                subreddits = [s.strip() for s in subreddits]
                scrape_multiple_subreddits(subreddits, force_update)
        
        elif command == "--help":
            print("\n📖 Usage:")
            print("  python scrape_subreddit_metadata.py --stats                    # Show statistics")
            print("  python scrape_subreddit_metadata.py --scrape wallstreetbets    # Scrape single subreddit")
            print("  python scrape_subreddit_metadata.py --scrape sub1,sub2,sub3   # Scrape multiple subreddits")
            print("  python scrape_subreddit_metadata.py --scrape subreddit --force # Force update regardless of time")
            print("  python scrape_subreddit_metadata.py --help                     # Show this help")
        
        else:
            print("❌ Invalid command. Use --help for usage instructions.")
    
    else:
        # Default: show stats and scrape wallstreetbets if needed
        print_subreddit_stats()
        print(f"\n🎯 Checking r/wallstreetbets metadata...")
        updated = scrape_and_save_subreddit_metadata("wallstreetbets")
        print(f"📊 Wallstreetbets metadata: {'Updated' if updated else 'No update needed'}") 