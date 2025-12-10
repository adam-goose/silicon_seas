from mable.examples import environment, fleets, companies
import numpy as np
import groupn


trades = np.arange(5,21)
fleetOptions = np.empty(21, dtype=int)
[np.append(fleetOptions, (i, j, k)) for i in range(1,22) for j in range(1,22) for k in range(1,22)]

def build_specification(trades_per_auction=10):
    number_of_month = 1

    #For when we are given a range of trades per auction:
    #trades_per_auction = np.arange(5, 10)
    
    


    specifications_builder = environment.get_specification_builder(trades_per_occurrence=trades_per_auction,num_auctions=number_of_month)
    my_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(groupn.CompanyZ6.Data(groupn.CompanyZ6, my_fleet, groupn.CompanyZ6.__name__))
    
    fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(companies.MyArchEnemy.Data(companies.MyArchEnemy, fleet, f"Arch Enemy Ltd.",profit_factor=1.5))
    
    the_scheduler_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    specifications_builder.add_company(companies.TheScheduler.Data(companies.TheScheduler, the_scheduler_fleet, f"The Scheduler LP",profit_factor=1.4))


    #Add 10 Arch Enemy and 10 Scheduler companies
    #Need to add varied fleet sizes
    # for company in range(1, 11):
    #     fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    #     specifications_builder.add_company(companies.MyArchEnemy.Data(companies.MyArchEnemy, fleet, f"Arch Enemy Ltd.{company}",profit_factor=1.5))
    
    #     the_scheduler_fleet = fleets.mixed_fleet(num_suezmax=1, num_aframax=1, num_vlcc=1)
    #     specifications_builder.add_company(companies.TheScheduler.Data(companies.TheScheduler, the_scheduler_fleet, f"The Scheduler LP {company}",profit_factor=1.4))
        
    sim = environment.generate_simulation(specifications_builder,show_detailed_auction_outcome=True,global_agent_timeout=60)
    sim.run()

if __name__ == '__main__':
    #Does 50 simulations as per the testing environment
    [build_specification() for i in range(1)]
    pass
