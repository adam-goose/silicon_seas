# harsh_agent/harsh_playground.py

from mable.examples import companies, environment, fleets

import groupn  # Adam's file (CompanyZ6 lives here)
from harsh_agent.harsh_company import HarshCompany


def build_specification():
    # 1 year, 12 auctions, 5 trades per auction (same as your main playground)
    number_of_months = 12
    trades_per_auction = 5

    specs = environment.get_specification_builder(
        trades_per_occurrence=trades_per_auction,
        num_auctions=number_of_months
    )

    # --- Harsh's fleet ---
    harsh_fleet = fleets.mixed_fleet(
        num_suezmax=1,
        num_aframax=1,
        num_vlcc=1
    )
    specs.add_company(
        HarshCompany.Data(
            HarshCompany,
            harsh_fleet,
            "Harsh Shipping Co."
        )
    )

    # --- Adam's fleet (baseline) ---
    adam_fleet = fleets.mixed_fleet(
        num_suezmax=1,
        num_aframax=1,
        num_vlcc=1
    )
    specs.add_company(
        groupn.CompanyZ6.Data(
            groupn.CompanyZ6,
            adam_fleet,
            "Adam Shipping Co."
        )
    )

    # Optional: also include benchmark companies if you like
    # (You can comment these out later if it’s too noisy.)

    arch_enemy_fleet = fleets.mixed_fleet(
        num_suezmax=1,
        num_aframax=1,
        num_vlcc=1
    )
    specs.add_company(
        companies.MyArchEnemy.Data(
            companies.MyArchEnemy,
            arch_enemy_fleet,
            "Arch Enemy Ltd.",
            profit_factor=1.5
        )
    )

    scheduler_fleet = fleets.mixed_fleet(
        num_suezmax=1,
        num_aframax=1,
        num_vlcc=1
    )
    specs.add_company(
        companies.TheScheduler.Data(
            companies.TheScheduler,
            scheduler_fleet,
            "The Scheduler LP",
            profit_factor=1.4
        )
    )

    # Build and run the simulation
    sim = environment.generate_simulation(
        specs,
        show_detailed_auction_outcome=True,
        global_agent_timeout=60
    )
    sim.run()


if __name__ == "__main__":
    build_specification()
