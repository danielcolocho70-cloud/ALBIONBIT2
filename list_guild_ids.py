#!/usr/bin/env python3
"""Script para listar todas las Guild IDs únicas en los eventos recientes"""

import asyncio
import aiohttp
import json

BASE = "https://gameinfo.albiononline.com/api/gameinfo"


async def list_all_guild_ids():
    url = f"{BASE}/events?limit=50"
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            events = await resp.json()
    
    guild_ids = {}  # {guild_id: {"name": "...", "count": 0}}
    
    print(f"\n📊 Analizando {len(events)} eventos...\n")
    
    for ev in events:
        killer = ev.get("Killer", {})
        victim = ev.get("Victim", {})
        
        # Extraer Guild IDs
        k_gid = killer.get("GuildId", "")
        k_name = killer.get("GuildName", "")
        k_player = killer.get("Name", "?")
        
        v_gid = victim.get("GuildId", "")
        v_name = victim.get("GuildName", "")
        v_player = victim.get("Name", "?")
        
        # Registrar killer
        if k_gid:
            if k_gid not in guild_ids:
                guild_ids[k_gid] = {"name": k_name, "count": 0, "players": set()}
            guild_ids[k_gid]["count"] += 1
            guild_ids[k_gid]["players"].add(k_player)
        
        # Registrar victim
        if v_gid:
            if v_gid not in guild_ids:
                guild_ids[v_gid] = {"name": v_name, "count": 0, "players": set()}
            guild_ids[v_gid]["count"] += 1
            guild_ids[v_gid]["players"].add(v_player)
    
    # Mostrar resultados ordenados por cantidad
    print("=" * 100)
    print(f"{'GUILD ID':<40} {'NOMBRE':<30} {'EVENTOS':<10} {'JUGADORES':<20}")
    print("=" * 100)
    
    for gid, data in sorted(guild_ids.items(), key=lambda x: x[1]["count"], reverse=True):
        print(f"{gid:<40} {data['name']:<30} {data['count']:<10} {len(data['players']):<20}")
    
    print("=" * 100)
    print(f"\nTotal de guilds únicas con actividad: {len(guild_ids)}")
    
    # Buscar la guild específica
    target_gid = "GxUSBm_FSayHELZWfI2nwA"
    if target_gid in guild_ids:
        print(f"\n✅ ENCONTRADA tu guild {target_gid}:")
        print(f"   Nombre: {guild_ids[target_gid]['name']}")
        print(f"   Eventos: {guild_ids[target_gid]['count']}")
    else:
        print(f"\n❌ Tu guild {target_gid} NO está en los últimos 50 eventos")
        print("\nTu guild no ha tenido kills/deaths recientemente o la Guild ID es incorrecta.")
        print("Espera a que tu guild tenga actividad PvP.")


if __name__ == "__main__":
    asyncio.run(list_all_guild_ids())
