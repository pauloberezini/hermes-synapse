import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.database import (
    db_get_rss_node,
    db_get_all_rss_nodes,
    db_save_rss_items,
    db_get_rss_items
)

logger = logging.getLogger("hermes.rss_service")

# Common default RSS feeds if user leaves feed_urls empty or creates a default node
DEFAULT_RSS_SOURCES = [
    ("Habr", "https://habr.com/ru/rss/news/"),
    ("RBC", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml")
]


def fetch_single_rss_feed(feed_url: str, timeout: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches XML from a single RSS/Atom feed URL and parses items into a standard dict format.
    """
    items = []
    feed_url = feed_url.strip()
    if not feed_url:
        return items

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 HermesRSS/1.0"
    }

    try:
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)

        # 1. RSS 2.0 channel -> item
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                guid_el = item.find("guid")
                pub_el = item.find("pubDate")

                title = title_el.text.strip() if title_el is not None and title_el.text else "Untitled"
                link = link_el.text.strip() if link_el is not None and link_el.text else feed_url
                summary = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                guid = guid_el.text.strip() if guid_el is not None and guid_el.text else (link or title)
                published_at = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

                items.append({
                    "feed_url": feed_url,
                    "guid": guid,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_at": published_at
                })
            return items

        # 2. Atom feed -> entry
        # Strip namespace if present
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall("atom:entry", ns) or root.findall("entry")
        for entry in entries:
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el = entry.find("atom:link", ns) or entry.find("link")
            desc_el = entry.find("atom:summary", ns) or entry.find("summary") or entry.find("atom:content", ns) or entry.find("content")
            id_el = entry.find("atom:id", ns) or entry.find("id")
            updated_el = entry.find("atom:updated", ns) or entry.find("updated") or entry.find("atom:published", ns) or entry.find("published")

            title = title_el.text.strip() if title_el is not None and title_el.text else "Untitled"
            
            link = feed_url
            if link_el is not None:
                link = link_el.attrib.get("href") or (link_el.text.strip() if link_el.text else feed_url)

            summary = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            guid = id_el.text.strip() if id_el is not None and id_el.text else (link or title)
            published_at = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

            items.append({
                "feed_url": feed_url,
                "guid": guid,
                "title": title,
                "link": link,
                "summary": summary,
                "published_at": published_at
            })

    except Exception as e:
        logger.warning(f"Error fetching RSS feed from {feed_url}: {e}")

    return items


def fetch_and_save_node_rss(node_id: str) -> Dict[str, Any]:
    """
    Fetches RSS entries for a specific node from all its configured URLs and writes to the DB table.
    """
    node = db_get_rss_node(node_id)
    if not node:
        return {"status": "error", "message": f"RSS node {node_id} not found", "inserted": 0}

    raw_urls = node.get("feed_urls", "")
    urls = [u.strip() for u in raw_urls.replace("\n", ",").split(",") if u.strip()]

    if not urls:
        # Fallback to default sources if empty
        urls = [src[1] for src in DEFAULT_RSS_SOURCES]

    all_items = []
    for url in urls:
        parsed_items = fetch_single_rss_feed(url)
        all_items.extend(parsed_items)

    inserted_count = db_save_rss_items(node_id, all_items)
    logger.info(f"RSS Node [{node_id}] '{node.get('name')}' sync complete. Fetched {len(all_items)} items, inserted {inserted_count} new entries.")

    return {
        "status": "success",
        "node_id": node_id,
        "name": node.get("name"),
        "total_parsed": len(all_items),
        "inserted": inserted_count,
        "last_fetched_at": datetime.now(timezone.utc).isoformat()
    }


def fetch_all_active_rss_nodes() -> List[Dict[str, Any]]:
    """
    Scans all active RSS nodes in the DB and triggers fetching for each.
    """
    nodes = db_get_all_rss_nodes()
    results = []
    for node in nodes:
        if node.get("is_active"):
            try:
                res = fetch_and_save_node_rss(node["id"])
                results.append(res)
            except Exception as e:
                logger.error(f"Error polling RSS node {node.get('id')}: {e}")
                results.append({"node_id": node.get("id"), "status": "error", "error": str(e)})
    return results


def get_rss_node_output(node_id: str, override_limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Gets the configured RSS output feed for agents connected to this node.
    Reflects the node's output_limit, date_filter_days, and keywords_filter settings.
    """
    node = db_get_rss_node(node_id)
    if not node:
        return {
            "node_id": node_id,
            "status": "error",
            "message": f"RSS node {node_id} not found",
            "items": []
        }

    limit = override_limit if override_limit is not None else node.get("output_limit", 10)
    date_filter = node.get("date_filter_days", 0)
    keywords = node.get("keywords_filter", "")

    items = db_get_rss_items(
        node_id=node_id,
        limit=limit,
        date_filter_days=date_filter,
        keywords_filter=keywords
    )

    return {
        "node_id": node_id,
        "name": node.get("name"),
        "status": "success",
        "output_limit": limit,
        "date_filter_days": date_filter,
        "keywords_filter": keywords,
        "last_fetched_at": node.get("last_fetched_at"),
        "count": len(items),
        "items": items
    }
