"""Test contract deposit"""
from stellar_sdk import SorobanServer, scval, Keypair, TransactionBuilder, Network
from stellar_sdk.soroban_rpc import GetTransactionStatus
import time

server = SorobanServer('https://soroban-testnet.stellar.org')
contract_id = 'CBEZLTP6IW3KETVKHHQIZP6MV4N5ROD3O2YMXE3WPDBHWYO53UBDJDFI'
dev_secret = 'SBJRCGYNBNMXHDZHIK4JWZUSUFKGLNZMVVGWWRNKTLQDL4DBEWBKXG62'
dev_public = 'GCF6SYQVT6F6AGOGAKKD4FYN7VEZI736B5F6GIKAE5CNWH2U4JJMFWOA'

keypair = Keypair.from_secret(dev_secret)
account = server.load_account(keypair.public_key)

print('Testing contract.deposit...')
tx = (
    TransactionBuilder(
        source_account=account,
        network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=100000,
    )
    .append_invoke_contract_function_op(
        contract_id=contract_id,
        function_name='deposit',
        parameters=[
            scval.to_uint64(0),
            scval.to_uint64(99999),
            scval.to_int128(10_000_000),  # 1 XLM
        ],
    )
    .set_timeout(300)
    .build()
)

sim = server.simulate_transaction(tx)
print(f'Simulation Error: {sim.error}')
if sim.results:
    print('Simulation OK - executing...')
    tx = server.prepare_transaction(tx)
    tx.sign(keypair)
    response = server.send_transaction(tx)
    print(f'Submitted: {response.hash}')
    for _ in range(20):
        time.sleep(1)
        result = server.get_transaction(response.hash)
        if result.status == GetTransactionStatus.SUCCESS:
            print('DEPOSIT SUCCESS!')
            break
        elif result.status == GetTransactionStatus.FAILED:
            print('DEPOSIT FAILED')
            break
else:
    print('Simulation failed')
