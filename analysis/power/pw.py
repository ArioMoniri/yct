import sys
import numpy as np
from statsmodels.stats.power import TTestIndPower
from scipy.stats import norm
P=TTestIndPower()
for n in (20,30,50):
    d2=P.solve_power(nobs1=n,alpha=.05,power=.8,ratio=1,alternative='two-sided')
    d1=P.solve_power(nobs1=n,alpha=.05,power=.8,ratio=1,alternative='larger')
    db=P.solve_power(nobs1=n,alpha=.05/7,power=.8,ratio=1,alternative='two-sided')
    # unbalanced 2:1 with total 2n
    du=P.solve_power(nobs1=int(2*n*2/3),alpha=.05,power=.8,ratio=0.5,alternative='two-sided')
    # AUC MDE vs 0.5 via Hanley-McNeil, binormal
    za,zb=norm.ppf(.975),norm.ppf(.8)
    def se(A,n1,n2):
        q1=A/(2-A);q2=2*A*A/(1+A)
        return np.sqrt((A*(1-A)+(n1-1)*(q1-A*A)+(n2-1)*(q2-A*A))/(n1*n2))
    se0=se(.5,n,n)
    for A in np.arange(.5,.95,.0005):
        if (A-.5) >= za*se0+zb*se(A,n,n): break
    print(n, f"d2={d2:.3f} d1={d1:.3f} dBonf7={db:.3f} d_unbal2:1={du:.3f} AUC_MDE={A:.3f} AUC(d2)={norm.cdf(d2/np.sqrt(2)):.3f}")

# D-053: label-free bounds for a given total N (no outcome split is used): `pw.py 53` prints the balanced
# split and the worst split the >= 20-per-group stop rule allows (N - 20 / 20). Two-sided alpha .05 single
# network; Holm worst case = alpha/4 (family H1-H3 + H4b); Bonferroni over the 7 H1 networks = alpha/7.
if len(sys.argv) > 1:
    Ntot = int(sys.argv[1])
    for n1, n2 in ((Ntot - Ntot // 2, Ntot // 2), (Ntot - 20, 20)):
        d = {a: P.solve_power(nobs1=n1, alpha=a, power=.8, ratio=n2 / n1, alternative='two-sided')
             for a in (.05, .05 / 4, .05 / 7)}
        print(f"N={Ntot} split {n1}/{n2}: d single={d[.05]:.3f} (AUC {norm.cdf(d[.05]/np.sqrt(2)):.3f}) "
              f"Holm worst (a/4)={d[.05/4]:.3f} Bonferroni 7={d[.05/7]:.3f}")
