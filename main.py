from fred import liquidity_canary

def run():
    trigger, conclusion, liq = liquidity_canary()
    print(trigger)
    print(conclusion)

if __name__ == "__main__":
    run()
