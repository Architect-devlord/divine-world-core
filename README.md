# Divine World 
> Proprietary World Simulation | AI-driven Minecraft Universe  
> Created by Devlord the Architect — All rights reserved

## 🌐 About
This version contains the full offline functional package of Divine World including logic systems, simulations, gods, bots, ai logic, and documentation.

## 🔐 Author and Rights
This project is under full ownership and copyright of Devlord the Architect (2025). It is NOT open source and is NOT for redistribution.

## 📦 Contents
- DivineWorld(Server side Forge Mod)
- DWClientBot(Client side Forge Mod)
- dw_agent(React frontend made for chatting and training)
- folder_definer
- License.txt (Full control license)
- Authorization.txt (Proof of authorship)
- README.md (This file)
- Ownership: See `Authorization.txt` and `License.txt`

 Do not distribute or modify without permission.

All rights reserved by Devlord the Architect.

# Setting up DivineWorld

## Manual Installations
1. Ollama and a lightweight model [phi3:mini, minstral, llama] (for other ai models add them in the list of agents in the DivineWorld mod)
2. Stuff in requirements.txt using pip and package.json using npm
3. Docker(Optional)(not really neccesary but go on if  you can manage the files for it the files here are incomplete and not updated)
4. Ultim MC (install minecraft 1.20.1 and download forge of version 47.4.10 for it)
5. Forge installer mdk

## Things to make sure before starting anything 
1. Have minimum 16GB RAM
2. Ollama daemon must be running

## Setting up
1. Clone the repo in a folder
2. Install forge server in a folder and name the folder DW_Server and make sure in that the onlinemode should be false in the server properties and use IPv4 in the user_jvm_args.txt and then move the folder to the folder in which the repo is cloned
3. Using the build function of the gradle create the server and client side mods of DivineWorld and DWClientBot respectively
4. Copy the server mod to the mods folder in DW_Server and from Ultim MC use view mods in the gui and then add the mod 
5. Start the minecraft server and run the main.py
6. Join the server by using minecraft and the server address is localhost
7. Use genesis and spawn gods(in their respective environments) and then enjoy 
