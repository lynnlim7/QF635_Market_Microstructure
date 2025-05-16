from decimal import getcontext, ROUND_HALF_UP

getcontext().prec = 38  # total digits of precision (like SQL Decimal(38,18))
getcontext().rounding = ROUND_HALF_UP