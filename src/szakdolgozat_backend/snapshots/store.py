

class Snapshot:
    """A snapshot of the database"""
    def __init__(self, DimAuthors, DimCategories, DimCurrencies, DimDates, DimSources, FactExchangeRates, FactNews):
        self.DimAuthors = DimAuthors
        self.DimCategories = DimCategories
        self.DimCurrencies = DimCurrencies
        self.DimDates = DimDates
        self.DimSources = DimSources
        self.FactExchangeRates = FactExchangeRates
        self.FactNews = FactNews

    def get_snapshot_memory(self) -> dict[str, int]:
        """returns the memory usage of the snapshot's tables in bytes"""
        total_memory = 0
        memory_usage = {}
        for attr, value in self.__dict__.items():
            if hasattr(value, "memory_usage"):
                memory_usage[attr] = int(value.memory_usage(index=True, deep=True).sum())
                total_memory += memory_usage[attr]

        memory_usage["total_memory"] = total_memory

        # Convert bytes to GiB
        for attr in memory_usage:
            memory_usage[attr] = round(memory_usage[attr] / (1024 ** 3), 4)

        memory_usage["total_memory"] = round(total_memory / (1024 ** 3), 4)

        return memory_usage