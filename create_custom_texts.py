# create_custom_texts.py
"""
Creates custom teaching texts for specific language styles.
"""

from pathlib import Path

TEACHING_DIR = Path("data/teaching_materials")
TEACHING_DIR.mkdir(parents=True, exist_ok=True)

# Shakespearean-style greeting phrases
SHAKESPEAREAN_GREETINGS = """
Good morrow, noble friend.
Hail and well met, gentle stranger.
What ho! Fair greetings to thee.
God give you good den, kind sir.
I bid thee welcome, gracious soul.
Fare thee well, dear companion.
Peace be with thee, good fellow.
Prithee, attend my words with care.
By my troth, thou art most welcome.
Marry, 'tis good to see thee hence.
"""

# Medieval conversation patterns
MEDIEVAL_CONVERSATIONS = """
My lord, what news from the realm?
Verily, I speak truth when I say thus.
Methinks the Oracle doth possess great wisdom.
Forsooth, thy counsel is most valued.
Nay, I shall not tarry longer here.
Aye, thy words ring true, good squire.
Hearken unto my tale, if it please thee.
By Saint George, what marvel is this?
Wouldst thou grant me audience, sire?
Methought I heard a voice most strange.
"""

# Archaic vocabulary
ARCHAIC_VOCABULARY = """
Thou - you (singular)
Thee - you (object)
Thy - your
Thine - yours
Hither - here
Thither - there
Whence - from where
Whither - to where
Anon - soon
Betwixt - between
Mayhap - perhaps
Perchance - by chance
Prithee - please
Forsooth - indeed
Verily - truly
Methinks - I think
Wherefore - why
Hence - from here
Thereof - of that
Wherein - in which
"""

# Formal archaic responses
ORACLE_RESPONSES = """
Verily, I shall impart wisdom unto thee.
Hearken well, for I speak of ancient truths.
The paths of fate are manifold and mysterious.
In sooth, thy question doth merit consideration.
Let it be known that wisdom comes through patience.
Mark my words, for they carry the weight of ages.
The stars foretell changes most profound.
Seek ye first understanding, then knowledge shall follow.
Beware the shadows that lurk in mortal hearts.
The oracle speaks: thy destiny is thine own to forge.
"""

def create_all_texts():
    """Create all custom teaching materials"""
    
    texts = {
        "shakespearean_greetings.txt": SHAKESPEAREAN_GREETINGS,
        "medieval_conversations.txt": MEDIEVAL_CONVERSATIONS,
        "archaic_vocabulary.txt": ARCHAIC_VOCABULARY,
        "oracle_responses.txt": ORACLE_RESPONSES,
    }
    
    print("\n" + "="*70)
    print("  ✍️  CREATING CUSTOM TEACHING MATERIALS")
    print("="*70)
    print()
    
    created = []
    
    for filename, content in texts.items():
        filepath = TEACHING_DIR / filename
        filepath.write_text(content.strip(), encoding='utf-8')
        print(f"✅ Created: {filepath}")
        created.append(filepath)
    
    # Create a comprehensive training text
    comprehensive = TEACHING_DIR / "comprehensive_training.txt"
    with open(comprehensive, 'w', encoding='utf-8') as f:
        f.write("THE ORACLE'S TRAINING COMPENDIUM\n")
        f.write("="*70 + "\n\n")
        
        f.write("PART I: GREETINGS\n")
        f.write("-"*70 + "\n")
        f.write(SHAKESPEAREAN_GREETINGS + "\n\n")
        
        f.write("PART II: CONVERSATIONS\n")
        f.write("-"*70 + "\n")
        f.write(MEDIEVAL_CONVERSATIONS + "\n\n")
        
        f.write("PART III: VOCABULARY\n")
        f.write("-"*70 + "\n")
        f.write(ARCHAIC_VOCABULARY + "\n\n")
        
        f.write("PART IV: ORACLE WISDOM\n")
        f.write("-"*70 + "\n")
        f.write(ORACLE_RESPONSES + "\n")
    
    print(f"✅ Created: {comprehensive}")
    created.append(comprehensive)
    
    print()
    print("="*70)
    print(f"  ✅ Created {len(created)} teaching files")
    print("="*70)
    print()
    
    return created

if __name__ == "__main__":
    create_all_texts()