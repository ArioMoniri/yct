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
