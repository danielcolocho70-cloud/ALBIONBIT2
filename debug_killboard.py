#!/usr/bin/env python3
"""Script para debuggear qué eventos y Guild IDs está recibiendo la API de Albion"""

import asyncio
import aiohttp
import json

BASE = "https://gameinfo.albiononline.com/api/gameinfo"


async def debug_events():
    url = f"{BASE}/events?limit=50"
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            events = await resp.json()
    
    print(f"\n📊 Total eventos recibidos: {len(events)}\n")
    
    # Mostrar primeros 5 eventos completos
    for i, ev in enumerate(events[:5]):
        print(f"\n{'='*80}")
        print(f"EVENTO {i+1}:")
        print(f"{'='*80}")
        print(json.dumps(ev, indent=2, ensure_ascii=False))
        
        # Extraer GuildIds
        killer = ev.get("Killer", {})
        victim = ev.get("Victim", {})
        print(f"\n>>> Killer GuildId: {killer.get('GuildId')}")
        print(f">>> Victim GuildId: {victim.get('GuildId')}")
        print(f">>> Killer Name: {killer.get('Name')}")
        print(f">>> Victim Name: {victim.get('Name')}")


if __name__ == "__main__":
    asyncio.run(debug_events())
