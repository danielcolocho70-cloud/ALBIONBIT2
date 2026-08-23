#!/usr/bin/env python3
"""Script para buscar Guild ID por nombre en Albion"""

import asyncio
import aiohttp
import json

BASE = "https://gameinfo.albiononline.com/api/gameinfo"


async def search_guild(guild_name: str):
    """Buscar guild por nombre y obtener su ID"""
    url = f"{BASE}/search?q={guild_name}"
    timeout = aiohttp.ClientTimeout(total=15)
    
    print(f"\n🔍 Buscando guild: {guild_name}\n")
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 400:
                    print("❌ Error 400: Solicitud incorrecta")
                    print("Intenta con un nombre más corto o específico")
                    return
                    
                resp.raise_for_status()
                data = await resp.json()
        except Exception as e:
            print(f"❌ Error de conexión: {e}")
            return
    
    # Procesar resultados
    guilds = data.get("Guilds", [])
    
    if not guilds:
        print(f"❌ No se encontraron guilds con el nombre '{guild_name}'")
        print("\nIntenta con:")
        print("  - Nombre más corto")
        print("  - Sin espacios al inicio/final")
        print("  - Parte del nombre exacto")
        return
    
    print(f"✅ Se encontraron {len(guilds)} guild(s):\n")
    print("=" * 100)
    print(f"{'#':<3} {'GUILD ID':<40} {'NOMBRE':<30} {'TAG':<10}")
    print("=" * 100)
    
    for i, guild in enumerate(guilds[:10], 1):
        gid = guild.get("Id", "N/A")
        name = guild.get("Name", "N/A")
        tag = guild.get("AllianceTag", "N/A")
        
        print(f"{i:<3} {gid:<40} {name:<30} {tag:<10}")
        
        if i == 1:
            print(f"\n💡 Guild ID correcta (probablemente): {gid}")
            print(f"   Usa esto en tu configuración del bot\n")
    
    print("=" * 100)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python search_guild.py <nombre_guild>")
        print("\nEjemplo:")
        print("  python search_guild.py \"REY DRAGON\"")
        sys.exit(1)
    
    guild_name = sys.argv[1]
    asyncio.run(search_guild(guild_name))
