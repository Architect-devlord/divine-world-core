# PROBLEMS

- ## Agent Packaging problem : (solved for npcs check for gods)
    Some how the packaging of the agents is always failing 

    *Confirmed error*  :
    The actuators.py's wait_for_conection() method is called before the UltimMC is packaged for the agent and started

    *Fix* :
    Use wait_for_connection() method after UltimMC along with the minecraft instance is launched
    
    *UltimMC commands*
    bash
    ```
    (dw_env) [devlord@architect bin]$ ./UltimMC --help
    Usage: ./UltimMC [-h] [-V] [-d <dir>] [-l <launch>] [-s <server>] [-w <world>] [-a <profile>] [-o] [-n <name>] [--alive] [-I <import>]

    Options & Switches:
    -h, --help            Display this help and exit.
    -V, --version         Display program version and exit.
    -d, --dir <dir>       Use the supplied folder as application root instead of the binary location (use '.' for current)
    -l, --launch <launch> Launch the specified instance (by instance ID)
    -s, --server <server> Join the specified server on launch (only valid in combination with --launch, mutually exclusive with --world)
    -w, --world <world>   Join the singleplayer world with the specified folder name on launch (only valid in combination with --launch, mutually exclusive with --server, only works with Minecraft 23w14a and later)
    -a, --profile <profile> Use the account specified by its profile name (only valid in combination with --launch)
    -o, --offline         Launch offline (only valid in combination with --launch)
    -n, --name <name>     When launching offline, use specified name (only makes sense in combination with --launch and --offline)
    --alive               Write a small 'live.check' file after the launcher starts
    -I, --import <import> Import instance from specified zip (local path or URL)
     
    ```
    *Preferred method* :
    Using the -s <localhost:25565> -l <1.20.1> -o <{agent_name}> tags when launching the agent in minecraft mode i.e during genesis and single agent creation of gods and npcs 

    Setting up the mods and creation of accounts and registring of agents are preconfigured

    check out this method in the packager.py in the script string 
    
    python
    ```
    def try_ultimmc(server_addr, agent_name):
    ult = AGENT_DIR / "UltimMC" / "bin" / "UltimMC"
    if not ult.exists():
        return False
    try:
        subprocess.Popen([
            str(ult), "-d", str(AGENT_DIR / "UltimMC"),
            "-l", agent_name, "-s", server_addr, "-a", agent_name, "-o", "-n", agent_name,
        ], cwd=str(AGENT_DIR))
        return True
    except Exception as e:
        log.error(f"UltimMC launch failed: {{e}}")
        return False
    ```

- ## Agent launching minecraft problem :(solved)
    The current codebase uses some other UltimMC script or executable and not the executable in the bin folder of the agents cause when the UltimMC launcher inside the agents' bin folder is used manually the accounts propely show up the mods are in the correct place and there is no prelaunching account creation java search required 

    *What was done*:

    From the terminal we go into the npc_applications folder and then an agents folder like say adam_1 and then inside its bin folder and then UltimMC is started then everything is already preconfigured correctly and there is no need of manually setting up anything
    bash
    ```
    cd npc_applications/adam_1/bin/UltimMC
    ./UltimMC
    ```
- ## Agent not able to control its body in minecraft:
    MAybe its the client side mod or the py_backend/ai_core dont really know about it and well need to check the agents' minecraft logs for solving this issue 

## The computer must be connected to the internet while agents are created so that the minecraft assets can be downloaded by UltimMC

## Note :
Create a remotely controlled agent without the brain to test the entire architecture like the frontend chat , control modes , minecraft control , etc where the user can send chat to the frontend user , control the minecraft body in minecraft using the control panel , access allowed websites via frontend , use the controller mode to control what the agent can basically there will be 2 users 1 will act as the normal user and the other one will act as the agent so the code architecture for the one who will act as an agent needs to be created 