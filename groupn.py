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

    # ============================================================
    #               INITIALISATION & SETUP
    # ============================================================

    # ---------------------- MULTI-START SETTINGS ----------------------
    MAX_SHUFFLES = 1            # max random permutations to try in multi-start
    
    # ---------------------- LNS SETTINGS ----------------------
    LNS_ENABLED      = True      # master switch
    LNS_ITERATIONS   = 10        # how many LNS tries per vessel
    LNS_REMOVALS     = 2         # how many trades to remove each time


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
    def propose_schedules(self, trades, post_auction=False):
        """
        Scheduling wrapper used by both:
        - inform()          → post_auction = False
        - receive()         → post_auction = True

        post_auction=False:
            Multi-start exploration for bidding.

        post_auction=True:
            Deterministic scheduling + LNS refinement
            (must schedule ALL won trades, zero penalties).
        """
        try:
            return self._propose_schedules_internal(trades, post_auction)
        except Exception as e:
            print("\n=== PROPOSE_SCHEDULES ERROR ===")
            print(type(e).__name__, e)
            raise


    # ============================================================
    #                  MULTI-START CONFIGURATION
    # ============================================================

    # Maximum number of shuffles to consider when trade count is small.

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

    def _propose_schedules_internal(self, trades, post_auction):
        """
        PRE-AUCTION (inform):
            - Multi-start permutations
            - Deterministic insertion
            - NO LNS

        POST-AUCTION (receive):
            - Deterministic insertion (must keep ALL trades)
            - Safe fallback if insertion drops trades
            - LNS refinement (only accepts full-trade schedules)
        """

        # ---------------------------------------------------------
        #                POST-AUCTION (receive)
        # ---------------------------------------------------------
        if post_auction:
            print("\n--- POST-AUCTION SCHEDULING PASS ---")

            required = set(trades)

            # 1. Deterministic insertion using current order
            base_result = self._single_insertion_pass(trades)
            base_set = set(base_result.scheduled_trades)

            # If ANY won trade is missing → try fallback
            if base_set != required:
                print("WARNING: Base insertion dropped trades. Trying fallback order.")
                reversed_order = list(trades)[::-1]
                fallback = self._single_insertion_pass(reversed_order)

                if set(fallback.scheduled_trades) == required:
                    base_result = fallback
                else:
                    print("CRITICAL: Both base and fallback failed to schedule all trades.")
                    # Return best possible schedule; avoid LNS that could worsen it.
                    return base_result

            # 2. LNS improvement on valid base solution
            if self.LNS_ENABLED:
                return self._apply_lns(base_result)

            return base_result

        # ---------------------------------------------------------
        #              PRE-AUCTION (inform)
        # ---------------------------------------------------------

        print("\n--- PRE-AUCTION MULTI-START SCHEDULING ---")

        n_trades = len(trades)
        K = self._adaptive_shuffle_count(n_trades)

        best_result = None
        best_score = float("inf")

        for _ in range(K):
            trial_trades = trades[:]
            random.shuffle(trial_trades)

            result = self._single_insertion_pass(trial_trades)

            score = (
                -1000 * len(result.scheduled_trades) +
                sum(s.completion_time() for s in result.schedules.values())
            )

            if score < best_score:
                best_score = score
                best_result = result

        return best_result


    def _apply_lns(self, initial_result):
        """
        Local Neighbourhood Search applied AFTER the auction.

        Guarantees:
            - NEVER drops a won trade
            - Only accepts candidates with full required set
            - Safe scoring (no trade-count bias)
            - Deterministic insertion + destroy/repair loops
        """

        required = set(initial_result.scheduled_trades)
        R = initial_result
        current_trades = list(R.scheduled_trades)

        def schedule_score(prop):
            return sum(s.completion_time() for s in prop.schedules.values())

        best_score = schedule_score(R)

        for _ in range(self.LNS_ITERATIONS):

            if not current_trades:
                break

            k = min(self.LNS_REMOVALS, len(current_trades))
            removed = random.sample(current_trades, k)
            kept = [t for t in current_trades if t not in removed]

            reinsertion_order = kept + removed

            candidate = self._single_insertion_pass(reinsertion_order)

            candidate_set = set(candidate.scheduled_trades)

            # HARD SAFETY CHECK — must include ALL required trades
            if candidate_set != required:
                continue

            cand_score = schedule_score(candidate)

            if cand_score < best_score:
                R = candidate
                current_trades = list(candidate.scheduled_trades)
                best_score = cand_score

        return R


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

        vessel_last_port = {}  # vessel → last destination port in this hypothetical schedule
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

                    # 1. Where is the vessel BEFORE this trade?
                    if vessel in vessel_last_port:
                        prev_loc = vessel_last_port[vessel]
                    else:
                        # No trades assigned yet – use the vessel's ACTUAL current port
                        prev_loc = vessel.location

                    # EMPTY travel
                    dist_empty = self.headquarters.get_network_distance(
                        prev_loc, trade.origin_port
                    )
                    t_empty = vessel.get_travel_time(dist_empty)
                    c_empty = vessel.get_ballast_consumption(t_empty, vessel.speed)

                    # Loading/unloading
                    load_t   = vessel.get_loading_time(trade.cargo_type, trade.amount)
                    load_c   = vessel.get_loading_consumption(load_t)
                    unload_c = vessel.get_loading_consumption(load_t)

                    # LOADED travel
                    dist_loaded = self.headquarters.get_network_distance(
                        trade.origin_port, trade.destination_port
                    )
                    t_loaded = vessel.get_travel_time(dist_loaded)
                    c_loaded = vessel.get_laden_consumption(t_loaded, vessel.speed)

                    # Total cost estimate
                    costs[trade] = float(c_empty + c_loaded + load_c + unload_c)

                    # Update vessel's last known location for next trade
                    vessel_last_port[vessel] = trade.destination_port


            # If no vessel can take the trade → drop it (normal behaviour)

        # Return normal MABLE object
        return ScheduleProposal(schedules, scheduled_trades, costs)


    # -------------------------------------------------------------
    #   Inform - BIDDING STRATEGY
    # -------------------------------------------------------------
    
    # --- Inform wrapper with error handling ---
    
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

    # --- Inform internal logic ---

    def _inform_internal(self, trades):
        proposal = self.propose_schedules(trades, post_auction=False)
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

    # -------------------------------------------------------------
    #   Receive - POST-AUCTION SCHEDULING
    # -------------------------------------------------------------

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        print("\n=== ENTERING CUSTOM RECEIVE ===")

        # Trades we actually won this auction
        trades = [c.trade for c in contracts]

        # POST-AUCTION scheduling pass (deterministic + LNS)
        scheduling_proposal = self.propose_schedules(trades, post_auction=True)

        # Apply schedule to environment – MABLE enforces feasibility
        rejected = self.apply_schedules(scheduling_proposal.schedules)

        if rejected:
            logger.error(f"{len(rejected)} rejected trades.")



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

