import asyncio
import json
import time
import sys

# --- CONFIGURATION ---
AGENTS = {
    "melchior-1": "melchior-1",
    "balthasar-2": "balthasar-2",
    "casper-3": "casper-3",
}

TIMEOUT_SECONDS = 120  # Reduced to avoid hanging too long

# --- CORE FUNCTIONS ---

async def call_agent(name: str, model: str, prompt: str):
    """Calls Ollama via subprocess."""
    start_time = time.time()
    process = None

    try:
        process = await asyncio.create_subprocess_exec(
            "ollama",
            "run",
            model,
            "--format", "json",
            "--hidethinking",  # Ensure no thought process leaks into output
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode()),
            timeout=TIMEOUT_SECONDS
        )

        elapsed = time.time() - start_time

        if process.returncode != 0:
            return {"agent": name, "status": "error", "error": stderr.decode().strip(), "latency": elapsed}

        try:
            # Parse the JSON output from Ollama
            parsed = json.loads(stdout.decode(errors="ignore"))
            
            # Normalize the output (we expect specific keys based on your prompt)
            # If the model wraps it in "response", we try to parse that inner string or use it directly
            if "claim" in parsed and "confidence" in parsed:
                return {"agent": name, "status": "ok", "output": parsed, "latency": elapsed}
            else:
                 # Fallback for unexpected structures
                return {"agent": name, "status": "ok", "output": parsed, "latency": elapsed}

        except json.JSONDecodeError as e:
            return {"agent": name, "status": "invalid_json", "raw": stdout.decode(), "error": str(e), "latency": elapsed}

    except asyncio.TimeoutError:
        if process:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
        return {"agent": name, "status": "timeout", "latency": TIMEOUT_SECONDS}

def create_bridge_prompt(agent_name, original_prompt, results_map):
    """
    Constructs the prompt for Round 2.
    It tells the agent what the OTHER two agents said.
    """
    others_text = ""
    for name, data in results_map.items():
        if name == agent_name:
            continue
        
        # Format the other agent's output for the prompt
        output = data.get('output', {})
        claim = output.get('claim', 'No claim provided')
        confidence = output.get('confidence', 0.0)
        failure_modes = output.get('failure_modes', [])
        
        others_text += f"\n**NODE {name.upper()} REPORT:**\n"
        others_text += f"- CLAIM: {claim}\n"
        others_text += f"- CONFIDENCE: {confidence}\n"
        others_text += f"- FAILURE MODES IDENTIFIED: {', '.join(failure_modes)}\n"

    new_prompt = (
        f"ORIGINAL INPUT: {original_prompt}\n\n"
        f"SYSTEM ALERT: DATA SYNCHRONIZATION PHASE.\n"
        f"The other MAGI nodes have processed the scenario. Review their outputs below:\n"
        f"{others_text}\n\n"
        f"DIRECTIVE: Re-evaluate your original calculation based on these variables. "
        f"If another node identifies a risk or advantage you missed, adjust your parameters. "
        f"Output your FINAL updated JSON analysis."
    )
    return new_prompt

async def run_magi_cycle(user_prompt: str):
    print(f"\n[MAGI_SYS] INITIALIZING ROUND 1: BLIND ANALYSIS...")
    
    # --- ROUND 1: PARALLEL CALLS ---
    tasks_r1 = [call_agent(name, model, user_prompt) for name, model in AGENTS.items()]
    results_r1_list = await asyncio.gather(*tasks_r1)
    
    # Map results by agent name for easy access
    results_r1_map = {r['agent']: r for r in results_r1_list if r['status'] == 'ok'}
    
    if len(results_r1_map) < 3:
        print("CRITICAL ERROR: Not all nodes responded in Round 1.")
        return

    print(f"[MAGI_SYS] ROUND 1 COMPLETE. SYNCHRONIZING DATA...")

    # --- ROUND 2: DEBATE / RE-EVALUATION ---
    tasks_r2 = []
    for name, model in AGENTS.items():
        # Create unique prompt for each agent containing the others' opinions
        bridge_prompt = create_bridge_prompt(name, user_prompt, results_r1_map)
        tasks_r2.append(call_agent(name, model, bridge_prompt))

    print(f"[MAGI_SYS] INITIALIZING ROUND 2: CROSS-REFERENCE & DEBATE...")
    results_r2_list = await asyncio.gather(*tasks_r2)
    
    # Process Final Results
    final_results = []
    for r in results_r2_list:
        if r['status'] == 'ok':
            final_results.append(r)
        else:
            # Fallback to Round 1 data if Round 2 fails for a node
            print(f"WARNING: Node {r['agent']} failed round 2. Using cached data.")
            final_results.append(results_r1_map[r['agent']])

    return final_results

def print_magi_report(results):
    print("\n" + "="*60)
    print("MAGI SYSTEM: FINAL DELIBERATION REPORT")
    print("="*60 + "\n")

    total_confidence = 0.0
    valid_nodes = 0

    # Print individual Node details
    for res in results:
        agent = res['agent'].upper()
        data = res.get('output', {})
        
        claim = data.get('claim', 'N/A')
        confidence = data.get('confidence', 0.0)
        
        # Color code based on agent
        prefix = ""
        if "MELCHIOR" in agent: prefix = "[SCIENTIST]"
        elif "BALTHASAR" in agent: prefix = "[MOTHER]"
        elif "CASPER" in agent: prefix = "[WOMAN]"

        print(f"{prefix} {agent}")
        print(f"CONFIDENCE: {confidence:.2f}")
        print(f"CLAIM: {claim}")
        print("-" * 30)

        total_confidence += confidence
        valid_nodes += 1

    # Calculate Consensus
    if valid_nodes > 0:
        avg_score = total_confidence / valid_nodes
    else:
        avg_score = 0.0

    print("\n" + "="*60)
    print(f"AGGREGATE CONFIDENCE SCORE: {avg_score:.4f}")
    
    status = ""
    if avg_score >= 0.7:
        status = ">> RESOLUTION: UNANIMOUS APPROVAL <<"
    elif avg_score >= 0.5:
        status = ">> RESOLUTION: MAJORITY APPROVAL (CONDITIONAL) <<"
    elif avg_score >= 0.3:
        status = ">> RESOLUTION: DEADLOCK / HUMAN INTERVENTION REQUIRED <<"
    else:
        status = ">> RESOLUTION: REJECTION <<"

    print(status)
    print("="*60 + "\n")

def main():
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
    else:
        print("\n--- MAGI SYSTEM TERMINAL ---")
        user_prompt = input("INPUT DIRECTIVE:\n> ")

    if not user_prompt:
        return

    final_data = asyncio.run(run_magi_cycle(user_prompt))
    print_magi_report(final_data)

if __name__ == "__main__":
    main()
