# report_playground/report_playground.py

import random
from datetime import datetime
from pathlib import Path

from mable.examples import companies, environment, fleets

# Agent versions (same folder)
from report_playground.agents.adam import (adam_v1_greedy, adam_v2_multistart,
                                           adam_v3_lns)
from report_playground.agents.harsh import harsh_v5_safe

# ----------------------------
# Parameters you specified
# ----------------------------

NUM_AUCTIONS = 24
# TRADES_PER_AUCTION_LIST = [48, 72, 96, 120, 144]
TRADES_PER_AUCTION_LIST = [48]
SHIPS_PER_COMPANY = 9
GLOBAL_TIMEOUT = 60

# How many different random worlds per setting (use this as your “scenario count”)
REPEATS_PER_SETTING = 1

# Output folder
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# ----------------------------
# Fleet helper (9 ships total)
# ----------------------------

def make_fleet_9():
    # 3 + 3 + 3 = 9 ships per company
    return fleets.mixed_fleet(
        num_suezmax=3,
        num_aframax=3,
        num_vlcc=3
    )


# ----------------------------
# Company add helper
# ----------------------------

def add_version(specs, agent_module, display_name: str):
    """
    Requires agent_module.COMPANY_CLASS = <ClassName>
    """
    cls = getattr(agent_module, "COMPANY_CLASS", None)
    if cls is None:
        raise RuntimeError(
            f"{agent_module.__name__} is missing COMPANY_CLASS. "
            f"Add: COMPANY_CLASS = <your company class>"
        )

    fleet = make_fleet_9()
    specs.add_company(cls.Data(cls, fleet, display_name))


def add_benchmarks(specs):
    """
    Same benchmarks you used before (optional but useful for context).
    """
    arch_enemy_fleet = make_fleet_9()
    specs.add_company(
        companies.MyArchEnemy.Data(
            companies.MyArchEnemy,
            arch_enemy_fleet,
            "Benchmark-ArchEnemy",
            profit_factor=1.5
        )
    )

    scheduler_fleet = make_fleet_9()
    specs.add_company(
        companies.TheScheduler.Data(
            companies.TheScheduler,
            scheduler_fleet,
            "Benchmark-TheScheduler",
            profit_factor=1.4
        )
    )


def run_all():
    run_id = 0

    for tpa in TRADES_PER_AUCTION_LIST:
        for rep in range(REPEATS_PER_SETTING):
            seed = random.randint(0, 100000)

            print(f"\n=== RUN {run_id} | TPA={tpa} | auctions={NUM_AUCTIONS} | ships={SHIPS_PER_COMPANY} | seed={seed} ===")

            specs = environment.get_specification_builder(
                trades_per_occurrence=tpa,
                num_auctions=NUM_AUCTIONS
            )

            # --- Our agent versions ---
            add_version(specs, adam_v1_greedy,   "Adam-V1-Greedy")
            add_version(specs, adam_v2_multistart, "Adam-V2-MultiStart")
            add_version(specs, adam_v3_lns,      "Adam-V3-LNS")
            add_version(specs, harsh_v5_safe,    "Harsh-V5-Latest")

            # --- Benchmarks (same as your old harsh playground) ---
            # add_benchmarks(specs)

            sim = environment.generate_simulation(
                specs,
                show_detailed_auction_outcome=False,
                global_agent_timeout=GLOBAL_TIMEOUT
            )

            sim.run()

            # Best-effort saving (depends on MABLE version)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = OUTPUT_DIR / f"report_metrics_run{run_id}_tpa{tpa}_seed{seed}_{ts}.json"

            if hasattr(sim, "metrics") and hasattr(sim.metrics, "save"):
                sim.metrics.save(out_path)
                print(f"Saved metrics -> {out_path}")
            else:
                print("Run complete. (This MABLE version did not expose sim.metrics.save().)")

            run_id += 1


if __name__ == "__main__":
    run_all()
# End of report_playground/report_playground.py