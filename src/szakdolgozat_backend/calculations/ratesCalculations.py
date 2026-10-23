def Avarage(Rates : list) -> float | None:
    """
    Function to calculate the average of a list of rates.

    Parameters:
    Rates (list): A list of numerical rates.

    Returns:
    float | None: The average of the rates, or None if the list is empty.
    """
    if not Rates:
        return None  # Return None if the list is empty

    total = sum(Rates)
    count = len(Rates)
    average = total / count
    return average

def ExchangePercentChange(currentRate : float | None, previousRate : float | None) -> float | None:
    """
    Function to calculate the percentage change between two rates.

    Parameters:
    currentRate (float): The current rate.
    previousRate (float): The previous rate.

    Returns:
    float | None: Returns a decimal ratio, matching the original DAX DIVIDE() calculation. For example, 0.05 represents a 5% change., or None if either rate is None or the previous rate is 0.
    """
    if currentRate is None or previousRate is None:
        return None

    if previousRate == 0:
        return None

    return (currentRate - previousRate) / previousRate

def WaterfallVarianceMonth(CurrentMonthRates : list, PreviousMonthRates : list) -> float | None:
    """
    Function to calculate the variance between two lists of rates for the current and previous month.

    Parameters:
    CurrentMonthRates (list): A list of numerical rates for the current month.
    PreviousMonthRates (list): A list of numerical rates for the previous month.

    Returns:
    float | None: The variance between the two lists of rates, or None if either list is empty.
    """
    if not CurrentMonthRates or not PreviousMonthRates:
        return None  # Return None if either list is empty

    current_average = Avarage(CurrentMonthRates)
    previous_average = Avarage(PreviousMonthRates)

    if current_average is None or previous_average is None:
        return None

    return current_average - previous_average  