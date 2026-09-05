"""All-time-high breakout sleeve: trail-only momentum on the Nifty Total Market.

A stock is bought the day it closes at a new 252-session high while still
sitting within 15% of its lifetime closing high, and is held until it gives
back a fixed fraction of the best close seen since entry. There is no profit
target, no time exit and no regime filter — the trailing stop is the entire
exit policy, which is what lets a small number of very large winners pay for
the roughly even split of round trips.
"""
