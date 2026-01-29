
import asyncio
import json
import time
import sys

AGENTS = {
    "melchior-1": "melchior-1",
    "balthasar-2": "balthasar-2",
    "casper-3": "casper-3",
}

TIMEOUT_SECONDS = 1040


async def call_agent(name: str, model: str, prompt: str):
    start_time = time.time()
    process = None

    try:
        process = await asyncio.create_subprocess_exec(
            "ollama",
            "run",
            model,
            "--format", "json",
            "--hidethinking",
            "--keepalive", "10m",
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
            return {
                "agent": name,
                "status": "error",
                "error": stderr.decode(errors="ignore").strip(),
                "latency": elapsed,
            }

        try:
            parsed = json.loads(stdout.decode(errors="ignore"))
            response_text = extract_payload(parsed)

            if not response_text:
                raise ValueError("Empty response field")

            return {
                "agent": name,
                "status": "ok",
                "output": response_text,
                "latency": elapsed,
            }

        except Exception as e:
            return {
                "agent": name,
                "status": "invalid_json",
                "raw_output": stdout.decode(errors="ignore"),
                "error": str(e),
                "latency": elapsed,
            }

    except asyncio.TimeoutError:
        if process:
            process.kill()
            await process.wait()

        return {
            "agent": name,
            "status": "timeout",
            "latency": TIMEOUT_SECONDS,
        }


async def run_magi(prompt: str):
    tasks = [
        call_agent(name, model, prompt)
        for name, model in AGENTS.items()
    ]
    return await asyncio.gather(*tasks)

def extract_payload(data: dict) -> dict:
    if "response" in data:
        return {"text": data["response"]}
    if "claim" in data:
        return data
    return {"raw": data}

def main():
    user_prompt = input("Pregunta para MAGI-mini:\n> ")
    results = asyncio.run(run_magi(user_prompt))

    print("\n=== RESULTADOS CRUDOS (SIN ARBITRAJE) ===\n")
    for r in results:
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
