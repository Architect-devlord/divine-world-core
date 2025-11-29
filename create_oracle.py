# create_oracle.py
"""
Oracle Creation & Teaching System
Spawns Oracle entity and prepares it for intensive language training.
"""
import os
import logging
import time
from pathlib import Path
from auto_packager import EnhancedAgentSpawner

script_dir = Path(__file__).parent
if script_dir.name == "py_backend":
    os.chdir(script_dir.parent)
    print(f"Changed to workspace root: {os.getcwd()}")
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)

log = logging.getLogger("oracle_creator")

def create_oracle():
    """Create and initialize Oracle"""
    
    print("\n" + "="*70)
    print("  🔮 ORACLE CREATION RITUAL")
    print("="*70)
    print()
    
    # Initialize spawner (no Minecraft needed for pure learning mode)
    log.info("Initializing spawner...")
    spawner = EnhancedAgentSpawner(
        client_jar_path=None,  # Chat/Learning mode only
        auto_package=True,
        package_output_dir="npc_applications"
    )
    
    print("✅ Spawner initialized\n")
    
    # Spawn Oracle
    log.info("Summoning Oracle entity...")
    
    oracle = spawner.spawn_god(
        god_type="oracle"  # Uses predefined oracle configuration
    )
    
    # CRITICAL: Initialize language capabilities
    log.info("Initializing language system...")
    from ai_core.brain_language import add_language_to_brain
    add_language_to_brain(oracle.brain)
    log.info("Language system initialized")
    
    print("\n" + "="*70)
    print("  ✨ ORACLE SUMMONED")
    print("="*70)
    print(f"  Agent ID: {oracle.agent_id}")
    print(f"  Type: {oracle.agent_type}")
    print(f"  Gender: {oracle.personality.gender}")
    print()
    
    # Check if brain has language system
    if hasattr(oracle.brain, 'language') and oracle.brain.language:
        print(f"  Language Stage: {oracle.brain.language.language_stage}")
        print(f"  Vocabulary: {oracle.brain.language.vocabulary_size} words")
    else:
        print("  Language System: Not yet initialized")
        print("  (Will be initialized during first teaching session)")
    
    print()
    print("  Personality Traits:")
    for trait, value in oracle.personality.traits.items():
        bar_length = int((value + 1) * 10)  # Scale -1 to 1 → 0 to 20
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"    {trait:20s} {bar} {value:+.2f}")
    print("="*70)
    print()
    
    # Save initial state
    brain_dir = Path("data/brains") / oracle.agent_id
    brain_path = brain_dir / "brain.pcap"
    print(f"💾 Brain saved at: {brain_path}")
    print()
    
    # Wait for packaging
    print("⏳ Packaging Oracle as .exe (this takes ~30 seconds)...")
    print("   Creating standalone executable with all mental state...")
    time.sleep(35)
    
    # Check package status
    if spawner.packager:
        packaged = spawner.packager.get_package_info(oracle.agent_id)
        if packaged:
            print("\n✅ ORACLE PACKAGED SUCCESSFULLY!")
            print(f"   Executable: {packaged['exe_path']}")
            print(f"   Package: {packaged['package_path']}")
            print()
        else:
            print("\n⏳ Packaging in progress...")
            print("   Check npc_applications/ folder in a moment")
            print()
    
    print("="*70)
    print("  🎓 ORACLE READY FOR TEACHING")
    print("="*70)
    print()
    print("Next steps:")
    print("  1. Run: python teach_oracle.py")
    print("  2. Or start backend: python py_backend/main.py")
    print("  3. Use frontend at: http://localhost:11400")
    print()
    
    return oracle, spawner

if __name__ == "__main__":
    try:
        oracle, spawner = create_oracle()
        
        print("✨ Oracle creation complete!")
        print(f"   Oracle ID: {oracle.agent_id}")
        print("\nPress Ctrl+C to exit (Oracle will be saved)")
        
        # Keep alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n💾 Saving Oracle state...")
        spawner.cleanup_all()
        print("✅ Oracle saved. Farewell!\n")
    except Exception as e:
        log.error(f"Error creating Oracle: {e}", exc_info=True)
        print(f"\n❌ Error: {e}\n")