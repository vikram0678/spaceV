"""
Web Scraping & Live Intelligence Tools for SpaceV.
Scrapes jobs, news headlines, weather, and encyclopedia summaries.
"""
import os
import csv
import json
import requests
import urllib.parse
from config import USER_DESKTOP_DIR

def scrape_jobs(role: str = "python", location: str = "remote", save_to_desktop: bool = True) -> str:
    """
    Scrapes real-time tech and remote jobs, formats top listings,
    and optionally exports them to a CSV file on your Desktop.
    """
    try:
        clean_role = role.strip().lower()
        # RemoteOK API (Public endpoint returning JSON listings)
        url = "https://remoteok.com/api"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return f"Job portal responded with status {response.status_code}. Try again in a moment."

        data = response.json()
        # First item in RemoteOK is legal notice, slice from 1:
        job_list = data[1:] if len(data) > 1 else []

        # Filter by keywords
        matched_jobs = []
        for job in job_list:
            position = job.get("position", "")
            tags = " ".join(job.get("tags", []))
            desc = job.get("description", "")
            full_text = f"{position} {tags} {desc}".lower()

            if clean_role in full_text or any(w in full_text for w in clean_role.split()):
                matched_jobs.append({
                    "Title": position,
                    "Company": job.get("company", "Unknown"),
                    "Location": job.get("location", "Remote"),
                    "Tags": ", ".join(job.get("tags", [])[:4]),
                    "URL": job.get("url", f"https://remoteok.com/l/{job.get('id', '')}")
                })

            if len(matched_jobs) >= 8:
                break

        if not matched_jobs:
            # Fallback if specific keyword didn't match
            matched_jobs = [{
                "Title": j.get("position", "Software Engineer"),
                "Company": j.get("company", "Tech Company"),
                "Location": j.get("location", "Remote"),
                "Tags": ", ".join(j.get("tags", [])[:4]),
                "URL": j.get("url", "https://remoteok.com")
            } for j in job_list[:5]]

        # Optionally save to CSV on Desktop
        csv_msg = ""
        if save_to_desktop and matched_jobs:
            csv_path = USER_DESKTOP_DIR / f"{clean_role.replace(' ', '_')}_jobs.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Title", "Company", "Location", "Tags", "URL"])
                writer.writeheader()
                writer.writerows(matched_jobs)
            csv_msg = f"\n\n📁 Saved {len(matched_jobs)} job listings to: {csv_path}"

        # Format readable summary
        summary = [f"Found {len(matched_jobs)} job listings for '{role}':\n"]
        for idx, job in enumerate(matched_jobs[:5], 1):
            summary.append(f"{idx}. **{job['Title']}** @ {job['Company']}")
            summary.append(f"   📍 {job['Location']} | 🏷️ {job['Tags']}")
            summary.append(f"   🔗 {job['URL']}\n")

        return "\n".join(summary) + csv_msg

    except Exception as e:
        return f"Failed to scrape jobs: {str(e)}"

def fetch_news_headlines(topic: str = "technology") -> str:
    """
    Fetches the latest top news headlines for a given topic or industry.
    """
    try:
        # Fetching tech news RSS feed via public aggregator
        query = urllib.parse.quote_plus(topic)
        url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage=5"
        
        res = requests.get(url, timeout=8)
        if res.status_code != 200:
            return "Could not retrieve news at this time."

        hits = res.json().get("hits", [])
        if not hits:
            return f"No breaking news found for '{topic}'."

        headlines = [f"Top headlines for '{topic}':\n"]
        for idx, item in enumerate(hits[:5], 1):
            title = item.get("title", "No Title")
            link = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('objectID')}"
            points = item.get("points", 0)
            headlines.append(f"{idx}. **{title}** (⭐ {points} pts)")
            headlines.append(f"   🔗 {link}\n")

        return "\n".join(headlines)
    except Exception as e:
        return f"Failed to fetch news: {str(e)}"

def get_weather(city: str = "") -> str:
    """
    Gets current weather conditions and temperature for the given city.
    """
    try:
        city_query = urllib.parse.quote_plus(city) if city else ""
        url = f"https://wttr.in/{city_query}?format=j1"
        
        headers = {"User-Agent": "curl/7.68.0"}
        res = requests.get(url, headers=headers, timeout=8)
        
        if res.status_code != 200:
            # Fallback text format
            text_res = requests.get(f"https://wttr.in/{city_query}?format=%l:+%c+%t,+%w+wind,+%h+humidity", timeout=8)
            return text_res.text if text_res.status_code == 200 else "Weather service currently unavailable."

        data = res.json()
        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]
        
        city_name = area.get("areaName", [{}])[0].get("value", city or "Local")
        country = area.get("country", [{}])[0].get("value", "")
        temp_c = current.get("temp_C", "N/A")
        temp_f = current.get("temp_F", "N/A")
        desc = current.get("weatherDesc", [{}])[0].get("value", "Clear")
        humidity = current.get("humidity", "N/A")
        wind = current.get("windspeedKmph", "N/A")

        return (
            f"🌤️ Weather for **{city_name}, {country}**:\n"
            f"• Condition: {desc}\n"
            f"• Temperature: {temp_c}°C ({temp_f}°F)\n"
            f"• Humidity: {humidity}%\n"
            f"• Wind Speed: {wind} km/h"
        )
    except Exception as e:
        return f"Failed to get weather: {str(e)}"

def get_wikipedia_summary(query: str) -> str:
    """
    Fetches a concise factual summary from Wikipedia about any person, topic, or concept.
    """
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        headers = {"User-Agent": "SpaceVDesktopAgent/1.0 (personal-assistant)"}
        
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            title = data.get("title", query)
            extract = data.get("extract", "No summary available.")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            return f"📖 **{title}** (Wikipedia):\n{extract}\n\n🔗 Read more: {page_url}"
        else:
            return f"No Wikipedia article found for '{query}'."
    except Exception as e:
        return f"Failed to search Wikipedia: {str(e)}"
