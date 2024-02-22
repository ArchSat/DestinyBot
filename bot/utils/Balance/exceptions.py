class NegativeBalanceException(Exception):
    def __init__(self, abs_balance, transaction_id, message='Недостаточно средств для выполнения операции!'):
        self.abs_balance = abs(abs_balance)
        self.transaction_id = transaction_id
        self.message = message
        super().__init__(self.message)
