from mable.cargo_bidding import TradingCompany
from mable.examples import environment, fleets


class MyCompany(TradingCompany):
    """Minimal company using default behaviour."""
    pass


if __name__ == "__main__":
    specifications_builder = environment.get_specification_builder(
        environment_files_path="."
    )
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(
        MyCompany.Data(
            MyCompany,
            fleet,
            "My Shipping Corp Ltd."
        )
    )
    sim = environment.generate_simulation(specifications_builder)
    sim.run()
