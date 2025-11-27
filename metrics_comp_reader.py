import os
import json
import matplotlib.pyplot as plt
from mable import cli
import numpy as np

#Set to current directory (should work on different machines)
os.chdir(os.getcwd())

def profit(metrics_file_name):

    #print(f"Overview for {metrics_file_name}.")
    with open(metrics_file_name, "r") as f:
        metrics = json.load(f)
    for one_company_key in metrics["company_metrics"]:
        company_name = metrics["company_names"][one_company_key]
        print(f"{company_name}")
        cost = 0
        if "fuel_cost" in metrics["company_metrics"][one_company_key]:
            cost = metrics["company_metrics"][one_company_key]["fuel_cost"]
        penalty = metrics["global_metrics"]["penalty"][one_company_key]
        revenue = 0
        all_outcomes = metrics["global_metrics"]["auction_outcomes"]
        all_outcomes_company_per_round = [d[one_company_key] for d in all_outcomes if one_company_key in d]
        all_outcomes_company = [x for sublist in all_outcomes_company_per_round for x in sublist]
        all_payments = [d["payment"] for d in all_outcomes_company]
        revenue += sum(all_payments)
        income = revenue - cost - penalty
        print(income)
        #return income


files = [f for f in os.listdir()
         if f.startswith("metrics_competition") and f.endswith(".json")]


plt.figure()
labels = []

for filename in files:
    profit(filename)
    with open(filename) as f:
        data = json.load(f)
    # print(dict(filename))
    # cli.task_metrics_overview(dict(filename))

    window_sums = []      # payment per auction window
    total_payment = 0
    fulfilled = 0
    unfulfilled = 0

    for auction in data["global_metrics"]["auction_outcomes"]:
        company_entry = auction.get("0", [])
        
        window_total = 0
        for contract in company_entry:
            p = contract.get("payment", 0)
            window_total += p
            total_payment += p

            if contract.get("fulfilled", False):
                fulfilled += 1
            else:
                unfulfilled += 1

        # if company 0 had no trades this window, window_total = 0
        window_sums.append(window_total)

    #print(f"{filename} => payment={total_payment:.2f}, " f"fulfilled={fulfilled}, unfulfilled={unfulfilled}")

    # cumulative over windows
    cumulative = []
    running = 0
    for w in window_sums:
        running += w
        cumulative.append(running)

    plt.plot(cumulative)
    labels.append(filename)

plt.title("Cumulative Payments per Auction Window (Company 0)")
plt.xlabel("Auction Window Index")
plt.ylabel("Cumulative Payment")
plt.grid(True)
plt.legend(labels)
plt.tight_layout()
#plt.show()
