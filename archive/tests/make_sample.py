# Creates a small synthetic CSV in the same format as the Kaggle file, for testing only.
# Usage: python make_sample.py <work_folder>/test/sample_trans.csv
import random, csv, sys
random.seed(7)
out = sys.argv[1]
banks = [str(b) for b in range(10, 60)]
accts = [(random.choice(banks), f"{random.getrandbits(36):09X}") for _ in range(3000)]
launder = random.sample(accts, 60)
fmts = ["Cheque","Credit Card","Wire","ACH","Cash","Reinvestment","Bitcoin"]
ccys = ["US Dollar","Euro","Yuan","Rupee"]
rows = []
for day in range(1, 6):
    for _ in range(12000):
        a, b = random.sample(accts, 2)
        amt = round(random.uniform(10, 5000), 2)
        c = random.choice(ccys) if random.random() < 0.1 else "US Dollar"
        rows.append((f"2022/09/0{day} {random.randint(0,23):02d}:{random.randint(0,59):02d}", a, b, amt, c, amt, "US Dollar", random.choice(fmts[:3]+["ACH"]) if random.random()<0.3 else "Cheque", 0))
    # laundering: fan-out then pass-through, cross currency, ACH
    for src in random.sample(launder, 15):
        mules = random.sample(launder, 6)
        for m in mules:
            if m == src: continue
            amt = round(random.uniform(5000, 9000), 2)
            rows.append((f"2022/09/0{day} 10:{random.randint(0,59):02d}", src, m, amt, "Euro", amt, "US Dollar", "ACH", 1))
            dst = random.choice(accts)
            rows.append((f"2022/09/0{day} 14:{random.randint(0,59):02d}", m, dst, amt*0.98, "Euro", amt*0.98, "Euro", "ACH", 1))
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Timestamp","From Bank","Account","To Bank","Account","Amount Received","Receiving Currency","Amount Paid","Payment Currency","Payment Format","Is Laundering"])
    for ts,a,b,ar,rc,ap,pc,fmt,l in rows:
        w.writerow([ts,a[0],a[1],b[0],b[1],ar,rc,ap,pc,fmt,l])
print(len(rows))
