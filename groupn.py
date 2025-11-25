import os
from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal

class CompanyZ6(TradingCompany):
    """
    A clean, minimal, coursework-safe agent.
    - Uses optimal insertion scheduling.
    - Bids exactly its estimated cost.
    - Never bids on trades it cannot schedule.
    - No heuristics, no future trades, no opponent modelling.
    """

    # -------------------------------------------------------------
    #   FUTURE TRADE HOOK (not used yet, but harmless to keep)
    # -------------------------------------------------------------
    def pre_inform(self, trades, time):
        """
        Called before the next auction.
        Currently only stores the future trades, unused for now.
        """
        self._future_trades = trades
        print(f"[{self.name}] received {len(trades)} future trades.")

    # -------------------------------------------------------------
    #   SCHEDULING WRAPPER
    # -------------------------------------------------------------
    def propose_schedules(self, trades):
        """
        Wrapper so we can print any scheduling errors clearly.
        """
        print("DEBUG: PROPOSE_SCHEDULES CALLED")
        try:
            return self._propose_schedules_internal(trades)
        except Exception as e:
            print("\n=== PROPOSE_SCHEDULES ERROR ===")
            print(type(e).__name__, e)
            raise

    # -------------------------------------------------------------
    #   CORE INSERTION SCHEDULING LOGIC
    # -------------------------------------------------------------
    def _propose_schedules_internal(self, trades):
        """
        For each trade:
          - try every vessel
          - try every pickup/dropoff combination in its schedule
          - keep the feasible schedule with minimum completion time
          - record that schedule + estimated cost

        Returned ScheduleProposal contains:
          - schedules:   {vessel : updated schedule}
          - scheduled_trades: list of trades we can actually do
          - costs:       {trade : estimated execution cost}
        """
        print("DEBUG: _PROPOSE_SCHEDULES_INTERNAL CALLED")

        schedules = {}          # vessel → updated Schedule
        scheduled_trades = []   # list of trades we CAN take
        costs = {}              # trade → cost
        self._trade_to_vessel = {} # trade → vessel mapping

        for trade in trades:

            for vessel in self._fleet:
                # Start from the current schedule (or the one we already updated)
                current = schedules.get(vessel, vessel.schedule)
                base = current.copy()

                best_schedule = None
                insertion_points = base.get_insertion_points()

                # Try all pickup/dropoff combinations
                for i, pickup in enumerate(insertion_points):
                    for dropoff in insertion_points[i:]:
                        test = base.copy()

                        # insert load + unload
                        test.add_transportation(
                            trade,
                            location_pick_up=pickup,
                            location_drop_off=dropoff
                        )

                        if not test.verify_schedule():
                            continue

                        # choose schedule with earliest completion time
                        if (
                            best_schedule is None or
                            test.completion_time() < best_schedule.completion_time()
                        ):
                            best_schedule = test

                # If feasible — assign to this vessel and stop searching
                if best_schedule:
                    schedules[vessel] = best_schedule
                    scheduled_trades.append(trade)

                    # store the vessel assigned to this trade
                    self._trade_to_vessel[trade] = vessel

                    # ---------------- Cost estimation ----------------
                    load_t = vessel.get_loading_time(trade.cargo_type, trade.amount)
                    load_c = vessel.get_loading_consumption(load_t)

                    # MABLE doesn't have unloading, so we mirror loading
                    unload_t = load_t
                    unload_c = vessel.get_loading_consumption(unload_t)

                    # Travel cost
                    dist = self.headquarters.get_network_distance(
                        trade.origin_port,
                        trade.destination_port
                    )
                    travel_t = vessel.get_travel_time(dist)
                    travel_c = vessel.get_laden_consumption(travel_t, vessel.speed)

                    total_cost = load_c + unload_c + travel_c
                    costs[trade] = float(total_cost)

                    break   # move to next trade

            # If no vessel can take the trade, we simply do not schedule it.

        return ScheduleProposal(schedules, scheduled_trades, costs)


    # -------------------------------------------------------------
    #   BIDDING STRATEGY  (CLEAN + SAFE)
    # -------------------------------------------------------------
    def inform(self, trades):
        """
        Bidding strategy:
          - For trades we CAN schedule: bid exactly our estimated cost
          - For trades we CANNOT schedule: do not bid
        """
        try:
            print("\n=== ENTERING CUSTOM INFORM ===")
            print("Trades:", trades)
            return self._inform_internal(trades)

        except Exception as e:
            import traceback
            print("\n=== ERROR INSIDE INFORM() ===")
            print(type(e).__name__, e)
            traceback.print_exc()
            raise

    # --- Find the vessel assigned to a trade ---
    def _find_vessel_for_trade(self, trade):
        """
        Currently unused, but may be helpful for future strategies.
        :return: vessel assigned to the trade, or None if not found
        """
        return self._trade_to_vessel.get(trade, None)

    def _inform_internal(self, trades):
        proposal = self.propose_schedules(trades)
        bids = []

        for trade in trades:

            # Skip if impossible
            if trade not in proposal.scheduled_trades:
                continue

            base_cost = proposal.costs[trade]

            # Find the vessel assigned to this trade in the proposed schedule
            vessel = self._find_vessel_for_trade(trade)

            bid_value = base_cost

            # Record the bid
            bids.append(Bid(amount=bid_value, trade=trade))

        return bids

# ---------------- SIMULATION BOOTSTRAP ----------------

if __name__ == "__main__":
    base_path = os.path.dirname(__file__)

    specs = environment.get_specification_builder(
        environment_files_path=base_path
    )

    fleet = fleets.example_fleet_1()

    specs.add_company(
        CompanyZ6.Data(
            CompanyZ6,
            fleet,
            "Baseline Shipping Corp"
        )
    )

    sim = environment.generate_simulation(specs)
    sim.run()

