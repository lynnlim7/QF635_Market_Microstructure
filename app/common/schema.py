import msgspec

class RiskSignalData(msgspec.Struct) : 
    order_type : str
    quantity : float
    price : float
