"""Transfer all vault balances to user's wallet"""
from stellar_sdk import Keypair, Server, TransactionBuilder, Network, Asset

server = Server("https://horizon-testnet.stellar.org")
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE

# User's wallet
USER_WALLET = "GDNNSWATM3WZMA23ABDLXYUOEVR45YG246WPNMTKX7NUFLOI6CLFEKUP"

# All vault and whale keys
ACCOUNTS = [
    # Bot Alpha
    {"name": "Bot Alpha Vault", "secret": "SBWZZ7IQFRVQSI4BNCM77OG263XOU2F2DFZKG4GT3R6XD4DQPWGU75RU"},
    {"name": "Bot Alpha Whale", "secret": "SB3WVSHEV3TFBLUDY2OJRU66FMMU3RK7EXKUZG2QT7AAX73TSLV6ICWL"},
    # Bot Beta
    {"name": "Bot Beta Vault", "secret": "SADKH7LPN2LN27QG4WQA7BTO4D7H5CJ5VXA7RZQ2YGZKWCAAYDXCN7II"},
    {"name": "Bot Beta Whale", "secret": "SCLSSHQCWNCS6H5MLEJQTVHRIDFOIEVMNCL3WFSBRKFLFOGONTZKDXVU"},
    # Bot Gamma
    {"name": "Bot Gamma Vault", "secret": "SDIBL2I7U4RH2N545NJBLCFQMIEI7EH6MLDH52QRDYO6FIVPFZ7MAZBE"},
    {"name": "Bot Gamma Whale", "secret": "SDH6GBD7NSULVWQIN7O7YAD3TV22WU3RC3WXIEF4R2SXOWAKLA3MQOTF"},
]

print(f"Transferring all balances to: {USER_WALLET}")
print("=" * 60)

total_sent = 0

for acc in ACCOUNTS:
    try:
        keypair = Keypair.from_secret(acc["secret"])
        public_key = keypair.public_key
        
        # Get account balance
        account_data = server.accounts().account_id(public_key).call()
        balance = float(next(
            (b['balance'] for b in account_data['balances'] if b['asset_type'] == 'native'),
            '0'
        ))
        
        # Leave 1.5 XLM for minimum balance + fee
        send_amount = balance - 1.5
        
        if send_amount <= 0:
            print(f"{acc['name']}: {balance:.2f} XLM (too low to transfer)")
            continue
        
        # Load account and build transaction
        source_account = server.load_account(public_key)
        
        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100
            )
            .append_payment_op(
                destination=USER_WALLET,
                asset=Asset.native(),
                amount=str(round(send_amount, 7))
            )
            .set_timeout(30)
            .build()
        )
        
        transaction.sign(keypair)
        response = server.submit_transaction(transaction)
        
        print(f"✓ {acc['name']}: Sent {send_amount:.2f} XLM")
        total_sent += send_amount
        
    except Exception as e:
        print(f"✗ {acc['name']}: Error - {e}")

print("=" * 60)
print(f"Total sent: {total_sent:.2f} XLM")
print(f"Destination: {USER_WALLET}")
