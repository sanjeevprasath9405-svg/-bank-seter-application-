IF OBJECT_ID('accounts', 'U') IS NULL
BEGIN
    CREATE TABLE accounts (
        id INT IDENTITY(1,1) PRIMARY KEY,
        account_no VARCHAR(20) NOT NULL,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) NOT NULL UNIQUE,
        password VARCHAR(255) NOT NULL,
        balance FLOAT NOT NULL DEFAULT 0
    );
END;

IF OBJECT_ID('transactions', 'U') IS NULL
BEGIN
    CREATE TABLE transactions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_id INT NOT NULL,
        transaction_type VARCHAR(20) NOT NULL,
        amount FLOAT NOT NULL,
        transaction_date DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_transactions_accounts
            FOREIGN KEY (user_id) REFERENCES accounts(id)
    );
END;
