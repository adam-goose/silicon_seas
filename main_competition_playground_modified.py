from mable.examples import environment, fleets, companies
import numpy as np
import groupn


def build_specification():
    number_of_month = 12
    trades_per_auction = 5
    #For when we are given a range of trades per auction:
    #trades_per_auction = np.arange(5, 10)
    
    specifications_builder = environment.get_specification_builder(trades_per_occurrence=trades_per_auction,num_auctions=number_of_month)
    my_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(groupn.CompanyZ6.Data(groupn.CompanyZ6, my_fleet, groupn.CompanyZ6.__name__))
    
    #Add 10 Arch Enemy and 10 Scheduler companies
    #Need to add varied fleet sizes
    for company in range(10):
        fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
        specifications_builder.add_company(companies.MyArchEnemy.Data(companies.MyArchEnemy, fleet, f"Arch Enemy Ltd.{company}",profit_factor=1.5))
    
        the_scheduler_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
        specifications_builder.add_company(companies.TheScheduler.Data(companies.TheScheduler, the_scheduler_fleet, f"The Scheduler LP {company}",profit_factor=1.4))
        
    sim = environment.generate_simulation(specifications_builder,show_detailed_auction_outcome=True,global_agent_timeout=60)
    sim.run()

if __name__ == '__main__':
    #Does 50 simulations as per the testing environment
    [build_specification() for i in range(50)]
