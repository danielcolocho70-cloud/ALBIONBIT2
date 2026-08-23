#!/usr/bin/env python3
"""Script para debuggear eventos del servidor Americas"""

import asyncio
import aiohttp
import json

# Usar el servidor Americas correctamente
BASE = "https://gameinfo-ams.albiononline.com/api/gameinfo"


async def debug_americas_events():
    """Obtener y mostrar eventos de Americas"""
    url = f"{BASE}/events?limit=50"
    timeout = aiohttp.ClientTimeout(total=15)
    
    print("🔍 Conectando a Americas (gameinfo-ams.albiononline.com)...\n")
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                events = await resp.json()
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    print(f"✅ Recibidos {len(events)} eventos\n")
    print("=" * 100)
    print(f"{'#':<3} {'KILLER GUILD ID':<40} {'KILLER NAME':<20} {'VICTIM GUILD ID':<40}")
    print("=" * 100)
    
    target_guild_id = "GxUSBm_FSayHELZWfI2nwA"
    found_target = False
    unique_guilds = set()
    
    for i, ev in enumerate(events[:20], 1):
        killer = ev.get("Killer", {})
        victim = ev.get("Victim", {})
        
        k_gid = killer.get("GuildId", "")
        k_name = killer.get("Name", "?")
        v_gid = victim.get("GuildId", "")
        
        print(f"{i:<3} {k_gid:<40} {k_name:<20} {v_gid:<40}")
        
        if k_gid:
            unique_guilds.add(k_gid)
        if v_gid:
            unique_guilds.add(v_gid)
        
        # Buscar la guild target
        if k_gid == target_guild_id or v_gid == target_guild_id:
            found_target = True
            role = "Killer" if k_gid == target_guild_id else "Victim"
            print(f"   ⭐ ENCONTRADA TU GUILD ({role})")
    
    print("=" * 100)
    print(f"\n📊 Resumen:")
    print(f"   Total eventos mostrados: 20")
    print(f"   Guilds únicas: {len(unique_guilds)}")
    print(f"\n🎯 Tu Guild ID: {target_guild_id}")
    
    if found_target:
        print(f"✅ ¡ENCONTRADA en los eventos! El killboard DEBERÍA funcionar.")
    else:
        print(f"❌ NO encontrada en los últimos 20 eventos")
        print(f"\n💡 Posibles razones:")
        print(f"   1. Tu guild no ha tenido kills/deaths recientemente")
        print(f"   2. La actividad está en otro servidor (Europe o Asia)")
        print(f"   3. Necesita actividad PvP para aparecer\n")
        print(f"   Guilds que SÍ tienen actividad:")
        for gid in list(unique_guilds)[:5]:
            print(f"   - {gid}")


if __name__ == "__main__":
    asyncio.run(debug_americas_events())
