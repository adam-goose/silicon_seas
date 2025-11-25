import os
import json
import matplotlib.pyplot as plt

os.chdir(r"B:\Google Drive Sync\UoS MSc Artificial Intelligence\Intelligent Agents\Labs\Lab 3")
print("Current working directory:", os.getcwd())

files = [f for f in os.listdir()
         if f.startswith("metrics_competition") and f.endswith(".json")]

plt.figure()
labels = []

for filename in files:
    with open(filename) as f:
        data = json.load(f)

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

    print(f"{filename} => payment={total_payment:.2f}, "
          f"fulfilled={fulfilled}, unfulfilled={unfulfilled}")

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
plt.show()
