# harsh_agent/harsh_company.py

import random

from mable.cargo_bidding import Bid, TradingCompany
from mable.transport_operation import ScheduleProposal


class HarshCompany(TradingCompany):
    """
    Harsh's shipping company agent.

    Version 5 overview:
    - Multi-start pre-auction scheduling:
        * tries several random orderings of the trades,
        * builds a schedule for each ordering,
        * keeps the schedule that looks best.
    - Insertion-based scheduling inside each start:
        * for each trade, tries every vessel and every insertion position,
        * keeps the earliest-completing feasible option.
    - Cost estimation per trade from loading and laden travel.
    - Bidding uses:
        * feasibility check from the scheduler,
        * time-window and distance filters,
        * heuristic scoring (cost, window length, distance, cargo size,
          future positioning),
        * bids only on the best few trades per auction,
        * cost-based pricing with a small undercut and random noise.
    """

    # -------- Pricing configuration --------
    PROFIT_MARGIN = 0.10        # desired markup over cost
    UNDERCUT_FACTOR = 0.02      # shave a bit off the margin
    RANDOM_BID_SPREAD = 0.02    # +/- 2% noise on bids

    # -------- Safety / selectivity --------
    MAX_BIDS_PER_AUCTION = 3    # max trades to bid on in one auction
    MIN_WINDOW_LENGTH = 360     # ignore trades with very tight time windows
    MAX_TRADE_DISTANCE = 60000  # ignore very long-haul trades

    # -------- Multi-start scheduling --------
    NUM_STARTS = 4              # how many random orderings to try (plus the original)
    START_SHUFFLE_SEED = 42     # base seed to keep behaviour reproducible-ish

    # -------- Future positioning influence --------
    FUTURE_POSITIONING_STRENGTH = 0.10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # trades announced for next auction
        self._future_trades = []
        # mapping trade -> vessel chosen in best schedule
        self._trade_to_vessel = {}

    # -------------------------------------------------
    #  Auction lifecycle
    # -------------------------------------------------
    def pre_inform(self, trades, time):
        """
        Called before the next auction.
        Just remember which trades are coming so we can think
        about where we want to end up (future positioning).
        """
        self._future_trades = list(trades)

    # -------------------------------------------------
    #  Scheduling (multi-start + insertion)
    # -------------------------------------------------
    def _build_schedule_for_order(self, trades_in_order):
        """
        Given a specific ordering of trades, build a schedule greedily:

        - Start from each vessel's current schedule.
        - For each trade (in the given order):
            * try all vessels and insertion points,
            * keep the earliest-completing feasible schedule,
            * if none works, skip the trade.

        Returns:
            schedules:        {vessel: updated schedule}
            scheduled_trades: [trades we managed to add]
            costs:            {trade: estimated_cost}
            score_tuple:      (-num_scheduled, total_cost, max_completion_time)
                               (used to compare different starts)
        """
        # start from copies of current schedules so one start
        # doesn't affect another
        schedules = {v: v.schedule.copy() for v in self._fleet}
        scheduled_trades = []
        costs = {}

        total_cost = 0.0
        max_completion_time = 0.0

        for trade in trades_in_order:
            best_vessel = None
            best_schedule = None

            for vessel in self._fleet:
                base_schedule = schedules[vessel]
                insertion_points = base_schedule.get_insertion_points()

                for i, pickup in enumerate(insertion_points):
                    for dropoff in insertion_points[i:]:
                        test_schedule = base_schedule.copy()
                        test_schedule.add_transportation(
                            trade,
                            location_pick_up=pickup,
                            location_drop_off=dropoff,
                        )

                        if not test_schedule.verify_schedule():
                            continue

                        if (
                            best_schedule is None
                            or test_schedule.completion_time()
                            < best_schedule.completion_time()
                        ):
                            best_schedule = test_schedule
                            best_vessel = vessel

            if best_schedule is None or best_vessel is None:
                # no vessel could take this trade in this start
                continue

            schedules[best_vessel] = best_schedule
            scheduled_trades.append(trade)

            # cost estimate for this trade on this vessel
            load_t = best_vessel.get_loading_time(
                trade.cargo_type, trade.amount
            )
            load_c = best_vessel.get_loading_consumption(load_t)

            unload_t = load_t
            unload_c = best_vessel.get_loading_consumption(unload_t)

            dist = self.headquarters.get_network_distance(
                trade.origin_port,
                trade.destination_port,
            )
            travel_t = best_vessel.get_travel_time(dist)
            travel_c = best_vessel.get_laden_consumption(
                travel_t, best_vessel.speed
            )

            trade_cost = float(load_c + unload_c + travel_c)
            costs[trade] = trade_cost
            total_cost += trade_cost

            max_completion_time = max(
                max_completion_time,
                best_schedule.completion_time(),
            )

        # fewer trades is worse, higher cost is worse, later completion is worse
        score_tuple = (
            -len(scheduled_trades),
            total_cost,
            max_completion_time,
        )

        return schedules, scheduled_trades, costs, score_tuple

    def _propose_schedules_internal(self, trades):
        """
        Multi-start wrapper around the greedy insertion scheduler.

        - Try one run with the original trade order.
        - Then try a few runs with randomly shuffled orders.
        - Keep the schedules from the start with the best score.
        """
        if not trades:
            return ScheduleProposal({}, [], {})

        best_schedules = None
        best_scheduled_trades = None
        best_costs = None
        best_score = None

        # 1) deterministic run with original order
        schedules, scheduled_trades, costs, score = self._build_schedule_for_order(
            list(trades)
        )
        best_schedules = schedules
        best_scheduled_trades = scheduled_trades
        best_costs = costs
        best_score = score

        # 2) a few randomised starts
        base_trades = list(trades)
        rng = random.Random(self.START_SHUFFLE_SEED)

        for _ in range(self.NUM_STARTS):
            rng.shuffle(base_trades)
            schedules, scheduled_trades, costs, score = self._build_schedule_for_order(
                base_trades
            )

            if best_score is None or score < best_score:
                best_score = score
                best_schedules = schedules
                best_scheduled_trades = scheduled_trades
                best_costs = costs

        # remember which vessel handles which trade (optional, but handy later)
        self._trade_to_vessel = {}
        for vessel, schedule in best_schedules.items():
            # we don't introspect the schedule here; just note that
            # any trade in best_costs belongs to some vessel in this dict.
            for trade in best_scheduled_trades:
                if trade in best_costs and trade not in self._trade_to_vessel:
                    # map loosely; we don't need exact per-vessel mapping
                    self._trade_to_vessel[trade] = vessel

        return ScheduleProposal(best_schedules, best_scheduled_trades, best_costs)

    def propose_schedules(self, trades):
        """
        Public entry point for the scheduler, with error reporting.
        """
        try:
            return self._propose_schedules_internal(trades)
        except Exception as e:
            import traceback

            print("\n[HarshCompany] Error in propose_schedules:")
            print(type(e).__name__, e)
            traceback.print_exc()
            raise

    # -------------------------------------------------
    #  Helpers for future positioning & scoring
    # -------------------------------------------------
    def _future_positioning_info(self, trade):
        """
        Compute basic information about how good this trade's destination
        is as a starting point for future trades.

        Returns:
            multiplier: factor to nudge price up/down (around 1.0)
            attractiveness: [0, 1] score used in heuristic trade scoring
        """
        if not self._future_trades:
            return 1.0, 0.0

        dest_port = trade.destination_port
        distances = [
            self.headquarters.get_network_distance(dest_port, ft.origin_port)
            for ft in self._future_trades
        ]

        if not distances:
            return 1.0, 0.0

        d_min = min(distances)

        # Convert distance into attractiveness in [0, 1]:
        # 1.0 when very close, 0.0 when very far
        attractiveness = max(0.0, 1.0 - d_min / 20000.0)

        multiplier = 1.0 + self.FUTURE_POSITIONING_STRENGTH * (0.5 - attractiveness)
        return multiplier, attractiveness

    def _score_trade(self, trade, base_cost):
        """
        Heuristic score for ranking trades before bidding.
        Higher is better.

        Components:
        - lower cost is better,
        - wider time windows are better,
        - shorter origin->destination distance is better,
        - larger cargo amount is better,
        - better future positioning is better.
        """
        # distance
        dist = self.headquarters.get_network_distance(
            trade.origin_port,
            trade.destination_port,
        )

        # time window length
        if hasattr(trade, "time_window") and trade.time_window:
            w_start = trade.time_window[0]
            w_end = trade.time_window[-1]
            window_length = max(0, w_end - w_start)
        else:
            window_length = 0

        cargo_amount = getattr(trade, "amount", 0)

        _, attractiveness = self._future_positioning_info(trade)

        # Weighted combination (tuned heuristically)
        score = 0.0
        score += -base_cost * 0.001
        score += window_length * 0.0004
        score += -dist * 0.0001
        score += cargo_amount * 0.05
        score += attractiveness * 5000.0

        return score

    # -------------------------------------------------
    #  Bidding
    # -------------------------------------------------
    def inform(self, trades):
        """
        Decide bids for the current auction.

        Steps:
        - Ask the scheduler which trades are feasible and what they cost.
        - For each trade:
            * skip if not feasible,
            * skip if its time window is very tight,
            * skip if origin->destination distance is very large.
        - Score the remaining trades heuristically.
        - Sort them by score and bid on at most MAX_BIDS_PER_AUCTION.
        - Bid price is based on cost, slightly undercut margin, future
          positioning and a small random noise.
        """
        proposal = self.propose_schedules(trades)
        candidates = []

        for trade in trades:
            if trade not in proposal.scheduled_trades:
                continue

            base_cost = proposal.costs[trade]

            # Filter 1: avoid very tight windows
            if hasattr(trade, "time_window") and trade.time_window:
                w_start = trade.time_window[0]
                w_end = trade.time_window[-1]
                window_length = max(0, w_end - w_start)
                if window_length < self.MIN_WINDOW_LENGTH:
                    continue

            # Filter 2: avoid very long voyages
            dist = self.headquarters.get_network_distance(
                trade.origin_port,
                trade.destination_port,
            )
            if dist > self.MAX_TRADE_DISTANCE:
                continue

            score = self._score_trade(trade, base_cost)
            candidates.append((score, trade, base_cost))

        # Sort high to low by score
        candidates.sort(key=lambda x: x[0], reverse=True)

        bids = []

        for idx, (score, trade, base_cost) in enumerate(candidates):
            if idx >= self.MAX_BIDS_PER_AUCTION:
                break

            # Base price: cost + (margin - undercut)
            effective_margin = self.PROFIT_MARGIN - self.UNDERCUT_FACTOR
            bid_value = base_cost * (1.0 + effective_margin)

            # Adjust based on future positioning
            position_multiplier, _ = self._future_positioning_info(trade)
            bid_value *= position_multiplier

            # Add a bit of noise so we're not perfectly predictable
            if self.RANDOM_BID_SPREAD > 0.0:
                noise = random.uniform(
                    -self.RANDOM_BID_SPREAD,
                    self.RANDOM_BID_SPREAD,
                )
                bid_value *= (1.0 + noise)

            bids.append(Bid(amount=bid_value, trade=trade))

        return bids

    # -------------------------------------------------
    #  Message handling
    # -------------------------------------------------
    def receive(self, messages):
        """
        Handle messages from the environment.
        For now we just use the default behaviour.
        """
        return super().receive(messages)
