import asyncio
import sys
import os

# Ensure backend can be imported
sys.path.append(os.getcwd())

from backend.council import run_full_council

async def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "What is the best coding model as of November 2025?"
        
    print(f"Running LLM Council with query: {query}")
    print("Please wait, this involves multiple stages of deliberation...")
    
    stage1, stage2, stage3, metadata = await run_full_council(query)
    
    print("\n" + "="*50)
    print("CHAIRMAN'S SYNTHESIS")
    print("="*50)
    print(stage3['response'])
    print("\n" + "="*50)
    print("AGGREGATE RANKINGS")
    print("="*50)
    for rank in metadata.get('aggregate_rankings', []):
        print(f"Rank {rank['average_rank']:.2f}: {rank['model']}")

if __name__ == "__main__":
    asyncio.run(main())
