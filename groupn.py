import os
from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal
import random

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

    # ============================================================
    #                  MULTI-START CONFIGURATION
    # ============================================================

    # Maximum number of shuffles to consider when trade count is small.
    MAX_SHUFFLES = 10

    def _adaptive_shuffle_count(self, n_trades):
        """
        Decide how many reshuffles to use depending on how
        many trades arrive in this auction.

        If we expect about 5–50 trades per auction.

        Strategy:
        - Few trades  (5–10): explore heavily (4–6 shuffles)
        - Medium      (11–25): moderate exploration (2–3)
        - Large       (26–50): light exploration (1–2)
        - Very large  (50+):   just 1 pass (too expensive)

        The goal: keep runtime low but still significantly improve
        final vessel allocation quality.
        """

        if n_trades <= 10:
            return self.MAX_SHUFFLES               # fully explore
        if n_trades <= 25:
            return max(3, self.MAX_SHUFFLES // 2)  # mid exploration
        if n_trades <= 50:
            return 2                                # minimal exploration
        return 1                                    # fallback for huge batches


    # ============================================================
    #                MULTI-START PROPOSAL WRAPPER
    # ============================================================

    def _propose_schedules_internal(self, trades):
        """
        MULTI-START INSERTION STRATEGY
        --------------------------------
        We try multiple *different random permutations* of the incoming
        trades and run the classic insertion logic on each one.

        Why?
        ----
        Insertion order has massive influence on final schedules.
        Some permutations yield far better vessel allocations.

        This wrapper:
        - Chooses K = adaptive_shuffle_count()
        - For each shuffle:
            * Randomise trade order
            * Perform deterministic insertion (single pass)
            * Score result by total completion time over all vessels
        - Return the best scoring result

        Importantly:
        ------------
        Costing, feasibility, constraints all remain identical.
        This ONLY improves the exploration of trade ordering.
        """

        print("DEBUG: MULTI-START _propose_schedules_internal")

        n_trades = len(trades)
        K = self._adaptive_shuffle_count(n_trades)

        best_result = None
        best_score = float("inf")

        for _ in range(K):
            # Randomised trade order for this attempt
            trial_trades = trades[:]
            random.shuffle(trial_trades)
            print("Trial trade order:", [t.origin_port.name for t in trial_trades])

            # Run deterministic insertion on this permutation
            result = self._single_insertion_pass(trial_trades)

            # Score based on sum of vessel completion times
            score = (
                -1000 * len(result.scheduled_trades) +     # more trades = better
                sum(s.completion_time() for s in result.schedules.values())
            )


            if score < best_score:
                best_score = score
                best_result = result

        return best_result


    # ============================================================
    #              ONE CLEAN INSERTION PASS (DETERMINISTIC)
    # ============================================================

    def _single_insertion_pass(self, trades):
        """
        This is your ORIGINAL insertion logic, isolated cleanly.

        For each trade in **given order**:
          - Try every vessel
          - Try every pickup/dropoff insertion point
          - Keep the feasible schedule with minimum completion time

        This function is deterministic assuming 'trades' order is fixed.
        """

        schedules = {}          # vessel → updated Schedule
        scheduled_trades = []   # trades successfully inserted
        costs = {}              # trade → cost estimate
        self._trade_to_vessel = {}  # for use in bidding

        for trade in trades:

            # Try assigning this trade to each vessel
            for vessel in self._fleet:

                # Either use schedule built during this pass or vessel's current schedule
                current = schedules.get(vessel, vessel.schedule)
                base = current.copy()

                best_schedule = None
                insertion_points = base.get_insertion_points()

                # Try every (pickup, dropoff) insertion pair
                for i, pickup in enumerate(insertion_points):
                    for dropoff in insertion_points[i:]:

                        test = base.copy()
                        test.add_transportation(
                            trade,
                            location_pick_up=pickup,
                            location_drop_off=dropoff
                        )

                        if not test.verify_schedule():
                            continue

                        # Choose insertion with lowest completion time
                        if (
                            best_schedule is None or
                            test.completion_time() < best_schedule.completion_time()
                        ):
                            best_schedule = test

                # If we found a feasible insertion → assign and cost it
                if best_schedule:
                    schedules[vessel] = best_schedule
                    scheduled_trades.append(trade)
                    self._trade_to_vessel[trade] = vessel

                    # ------------ COST CALCULATION ------------
                    load_t   = vessel.get_loading_time(trade.cargo_type, trade.amount)
                    load_c   = vessel.get_loading_consumption(load_t)
                    unload_c = vessel.get_loading_consumption(load_t)  # symmetric

                    dist      = self.headquarters.get_network_distance(
                        trade.origin_port, trade.destination_port
                    )
                    travel_t  = vessel.get_travel_time(dist)
                    travel_c  = vessel.get_laden_consumption(travel_t, vessel.speed)

                    costs[trade] = float(load_c + unload_c + travel_c)

                    break  # trade assigned → move to next trade

            # If no vessel can take the trade → drop it (normal behaviour)

        # Return normal MABLE object
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

