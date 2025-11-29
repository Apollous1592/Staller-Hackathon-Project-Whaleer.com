"""
Profit Sharing App - Python Backend
Flask API server with Stellar testnet integration
Soroban Smart Contract for automated commission distribution
Demo for Whaleer.com profit-sharing system
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from stellar_sdk import Keypair, Server, TransactionBuilder, Network, Asset
from stellar_sdk import SorobanServer, scval
from stellar_sdk.soroban_rpc import GetTransactionStatus
from stellar_sdk.exceptions import NotFoundError, BadRequestError
from decimal import Decimal
import random
import time
import requests

# ============== XLM PRICE CACHE ==============
xlm_price_cache = {
    'price': 0.40,  # fallback price
    'last_updated': 0
}

def get_xlm_usd_price():
    """Fetch real-time XLM/USD price from CoinGecko API with 60s cache"""
    global xlm_price_cache
    
    # Cache for 60 seconds to avoid rate limiting
    if time.time() - xlm_price_cache['last_updated'] < 60:
        return xlm_price_cache['price']
    
    try:
        # CoinGecko free API - no key needed
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids': 'stellar', 'vs_currencies': 'usd'},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            price = data.get('stellar', {}).get('usd', 0.40)
            xlm_price_cache['price'] = price
            xlm_price_cache['last_updated'] = time.time()
            print(f"[XLM PRICE] Updated: ${price:.4f}")
            return price
    except Exception as e:
        print(f"[XLM PRICE] Error fetching price: {e}")
    
    # Return cached or fallback price
    return xlm_price_cache['price']

app = Flask(__name__)
CORS(app)

# Stellar Testnet Configuration
HORIZON_URL = "https://horizon-testnet.stellar.org"
SOROBAN_RPC_URL = "https://soroban-testnet.stellar.org"
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE

# Initialize Stellar servers
server = Server(horizon_url=HORIZON_URL)
soroban_server = SorobanServer(SOROBAN_RPC_URL)

# ============== SOROBAN CONTRACT CONFIG ==============
# Developer wallet that receives profit commissions
DEVELOPER_PUBLIC_KEY = "GARPOAGOQSJEN3ODZSDZZT63PLDXDP6QN5PVHY3CD4JMITGUMQPR2MGH"

# Platform/Admin wallet (for platform cut and signing init_vault)
PLATFORM_PUBLIC_KEY = "GCF6SYQVT6F6AGOGAKKD4FYN7VEZI736B5F6GIKAE5CNWH2U4JJMFWOA"
PLATFORM_SECRET_KEY = "SBJRCGYNBNMXHDZHIK4JWZUSUFKGLNZMVVGWWRNKTLQDL4DBEWBKXG62"

# Smart Contract ID (deployed on Stellar Testnet)
CONTRACT_ID = "CBEZLTP6IW3KETVKHHQIZP6MV4N5ROD3O2YMXE3WPDBHWYO53UBDJDFI"

# Native XLM Asset ID on Soroban
NATIVE_ASSET_ID = "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC"

# In-memory storage
user_sessions = {}

# Trading Bots - Her bot için developer adresi ve komisyon oranları
# total_commission_rate: Kârın yüzde kaçı toplam komisyon olarak kesilecek
# platform_cut_percent: Toplam komisyonun yüzde kaçı platform'a gidecek (developer'dan kesilir)
# Contract'a gönderilecek değerler hesaplanır (profit_share_bps, platform_cut_bps)
TRADING_BOTS = [
    {
        "id": "bot-alpha",
        "name": "Bot Alpha",
        "strategy": "Trend Following - EMA crossovers",
        "total_commission_rate": 10,  # Kârın %10'u toplam komisyon
        "platform_cut_percent": 10,   # Komisyonun %10'u platform'a (developer'dan kesilir)
        # Developer net: %9, Platform: %1 (toplam %10)
        "min_commission_deposit": 10,
        "developer": DEVELOPER_PUBLIC_KEY,
        "platform": PLATFORM_PUBLIC_KEY,
    },
    {
        "id": "bot-beta",
        "name": "Bot Beta", 
        "strategy": "Arbitrage - Cross-exchange",
        "total_commission_rate": 10,  # Kârın %10'u toplam komisyon
        "platform_cut_percent": 10,   # Komisyonun %10'u platform'a (developer'dan kesilir)
        # Developer net: %9, Platform: %1 (toplam %10)
        "min_commission_deposit": 5,
        "developer": DEVELOPER_PUBLIC_KEY,
        "platform": PLATFORM_PUBLIC_KEY,
    },
    {
        "id": "bot-gamma",
        "name": "Bot Gamma",
        "strategy": "DCA - Smart timing",
        "total_commission_rate": 10,  # Kârın %10'u toplam komisyon
        "platform_cut_percent": 10,   # Komisyonun %10'u platform'a (developer'dan kesilir)
        # Developer net: %9, Platform: %1 (toplam %10)
        "min_commission_deposit": 5,
        "developer": DEVELOPER_PUBLIC_KEY,
        "platform": PLATFORM_PUBLIC_KEY,
    },
]

# Starting simulation balance
STARTING_SIMULATION_BALANCE = 100.0  # $100 virtual money

# ============== HELPER FUNCTIONS ==============

def get_bot_index(bot_id: str) -> int:
    """Get bot index from bot_id string"""
    return next((i for i, b in enumerate(TRADING_BOTS) if b['id'] == bot_id), 0)

def get_user_hash(user_public_key: str) -> int:
    """Create a consistent user ID from public key"""
    return hash(user_public_key) % 1000000

def get_user_session(user_public_key):
    """Get or create user session"""
    if user_public_key not in user_sessions:
        user_sessions[user_public_key] = {
            "public_key": user_public_key,
            "active_bots": {}
        }
    return user_sessions[user_public_key]

def generate_daily_performance():
    """Generate random daily performance between -3% and +5%"""
    return round(random.uniform(-3.0, 5.0), 2)

def calculate_contract_rates(total_commission_rate: float, platform_cut_percent: float):
    """
    Developer'ın belirlediği toplam komisyon oranından contract'a gönderilecek
    profit_share_bps ve platform_cut_bps hesaplar.
    
    Yeni mantık:
    - Developer %10 komisyon belirlemiş
    - Platform sabit %10 alıyor (developer'ın payından)
    
    Örnek: total_commission_rate=10, platform_cut_percent=10
    - Kullanıcıdan kesilen: %10
    - Platform: %10'un %10'u = %1
    - Developer net: %10 - %1 = %9
    
    Contract'a:
    - profit_share_bps = 1000 (%10 toplam komisyon)
    - platform_cut_bps = 1000 (%10 of commission goes to platform)
    """
    profit_share_bps = int(total_commission_rate * 100)  # %10 → 1000
    platform_cut_bps = int(platform_cut_percent * 100)   # %10 → 1000
    
    return profit_share_bps, platform_cut_bps

# ============== SOROBAN CONTRACT FUNCTIONS ==============

def invoke_contract_with_simulation(function_name: str, params: list, signer_secret: str):
    """
    Arkadaşın init_vault.py'den adapte edildi.
    Önce simülasyon yapar, hataları detaylı loglar, sonra gönderir.
    """
    try:
        signer_keypair = Keypair.from_secret(signer_secret)
        
        # Horizon'dan sequence number al (arkadaşın yöntemi)
        source_account = server.load_account(signer_keypair.public_key)
        
        tx = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,  # Simülasyon sonrası artabilir
            )
            .set_timeout(30)
            .append_invoke_contract_function_op(
                contract_id=CONTRACT_ID,
                function_name=function_name,
                parameters=params,
            )
            .build()
        )
        
        # Simülasyon yap (arkadaşın eklediği özellik)
        print(f"⏳ Simülasyon yapılıyor: {function_name}...")
        sim_resp = soroban_server.simulate_transaction(tx)
        
        # Simülasyon hata kontrolü
        if hasattr(sim_resp, 'error') and sim_resp.error:
            print(f"🔴 Simulation Error: {sim_resp.error}")
            raise RuntimeError(f"Simülasyon Başarısız: {sim_resp.error}")
        
        print(f"✅ Simülasyon başarılı!")
        
        # Simülasyon verilerini işleme ekle
        tx = soroban_server.prepare_transaction(tx, sim_resp)
        
        # İmzala
        tx.sign(signer_keypair)
        
        # Gönder
        print(f"🚀 İşlem ağa gönderiliyor: {function_name}...")
        response = soroban_server.send_transaction(tx)
        
        if hasattr(response, 'status') and response.status == "ERROR":
            raise RuntimeError(f"Transaction Failed: {response}")
        
        print(f"[CONTRACT] {function_name} submitted: {response.hash}")
        
        tx_hash = response.hash
        for _ in range(30):
            time.sleep(1)
            result = soroban_server.get_transaction(tx_hash)
            if result.status == GetTransactionStatus.SUCCESS:
                print(f"✅ [CONTRACT] {function_name} SUCCESS!")
                return result
            elif result.status == GetTransactionStatus.FAILED:
                print(f"❌ [CONTRACT] {function_name} FAILED")
                return None
        
        return None
        
    except Exception as e:
        print(f"🔴 [CONTRACT] Error in {function_name}: {e}")
        return None


def invoke_contract(function_name: str, params: list, signer_secret: str):
    """Generic function to invoke Soroban smart contract methods (eski versiyon)"""
    try:
        signer_keypair = Keypair.from_secret(signer_secret)
        source_account = soroban_server.load_account(signer_keypair.public_key)
        
        tx = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100000,
            )
            .append_invoke_contract_function_op(
                contract_id=CONTRACT_ID,
                function_name=function_name,
                parameters=params,
            )
            .set_timeout(300)
            .build()
        )
        
        tx = soroban_server.prepare_transaction(tx)
        tx.sign(signer_keypair)
        response = soroban_server.send_transaction(tx)
        
        print(f"[CONTRACT] {function_name} submitted: {response.hash}")
        
        tx_hash = response.hash
        for _ in range(30):
            time.sleep(1)
            result = soroban_server.get_transaction(tx_hash)
            if result.status == GetTransactionStatus.SUCCESS:
                print(f"[CONTRACT] {function_name} SUCCESS!")
                return result
            elif result.status == GetTransactionStatus.FAILED:
                print(f"[CONTRACT] {function_name} FAILED")
                return None
        
        return None
        
    except Exception as e:
        print(f"[CONTRACT] Error in {function_name}: {e}")
        return None


def contract_init_vault(
    bot_id: int,
    user_id: int,
    user_address: str,
    developer_address: str,
    total_commission_rate: float = 10,  # Developer'ın belirlediği toplam oran
    platform_cut_percent: float = 10,   # Sabit %10 platform kesintisi
):
    """
    Soroban kontratındaki init_vault fonksiyonunu çağırır.
    
    Yeni davranış:
    - Developer %10 komisyon belirlemiş
    - Platform sabit %10 alıyor (developer'ın payından)
    
    Örnek: 100 XLM kâr
    - Toplam komisyon: 10 XLM (%10)
    - Platform: 1 XLM (%10 of 10 XLM)
    - Developer net: 9 XLM
    """
    # Platform rate hesapla (gösterim için)
    platform_rate = total_commission_rate * platform_cut_percent / 100
    developer_net = total_commission_rate - platform_rate
    
    print(f"\\n{'='*60}")
    print("🔧 INIT VAULT - Soroban Contract Call")
    print(f"{'='*60}")
    print(f"Bot ID: {bot_id}")
    print(f"User ID: {user_id}")
    print(f"User Address: {user_address}")
    print(f"Developer Address: {developer_address}")
    print(f"Platform Address: {PLATFORM_PUBLIC_KEY}")
    print(f"Total Commission Rate: {total_commission_rate}% of profit")
    print(f"Platform Cut: {platform_cut_percent}% of commission → {platform_rate}% of profit")
    print(f"Developer Net: {developer_net}% of profit")
    
    # Contract'a gönderilecek BPS değerlerini hesapla
    profit_share_bps, platform_cut_bps = calculate_contract_rates(total_commission_rate, platform_cut_percent)
    
    print(f"→ profit_share_bps: {profit_share_bps} (toplam komisyon oranı)")
    print(f"→ platform_cut_bps: {platform_cut_bps} (platform'un komisyondan aldığı pay)")
    
    # Validation
    if profit_share_bps < 0 or platform_cut_bps < 0:
        raise ValueError("Oranlar negatif olamaz.")
    if profit_share_bps > 10_000 or platform_cut_bps > 10_000:
        raise ValueError("Oranlar %100 (10000 bps) üzerinde olamaz.")
    
    # fn init_vault(env, bot_id, user_id, user_address, developer, platform, asset, profit_share_bps, platform_cut_bps)
    params = [
        scval.to_uint64(bot_id),
        scval.to_uint64(user_id),
        scval.to_address(user_address),
        scval.to_address(developer_address),     # developer - kar payı buraya
        scval.to_address(PLATFORM_PUBLIC_KEY),   # platform - platform kesintisi buraya
        scval.to_address(NATIVE_ASSET_ID),       # asset (XLM)
        scval.to_uint32(profit_share_bps),       # toplam komisyon oranı
        scval.to_uint32(platform_cut_bps),       # platform'un payı
    ]
    
    return invoke_contract_with_simulation("init_vault", params, PLATFORM_SECRET_KEY)


def contract_deposit(bot_id: int, user_id: int, amount_xlm: float, user_public_key: str):
    """
    Create contract deposit XDR for user to sign
    Returns XDR that frontend will sign with Freighter
    """
    try:
        amount_stroops = int(amount_xlm * 10_000_000)
        
        source_account = soroban_server.load_account(user_public_key)
        
        params = [
            scval.to_uint64(bot_id),
            scval.to_uint64(user_id),
            scval.to_int128(amount_stroops),
        ]
        
        tx = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100000,
            )
            .append_invoke_contract_function_op(
                contract_id=CONTRACT_ID,
                function_name="deposit",
                parameters=params,
            )
            .set_timeout(300)
            .build()
        )
        
        tx = soroban_server.prepare_transaction(tx)
        
        print(f"[CONTRACT] Deposit XDR created: {amount_xlm} XLM")
        return tx.to_xdr(), None
        
    except Exception as e:
        print(f"[CONTRACT] Deposit XDR error: {e}")
        return None, str(e)


def contract_withdraw(bot_id: int, user_id: int, amount_xlm: float, user_public_key: str):
    """Create contract withdraw XDR for user to sign"""
    try:
        amount_stroops = int(amount_xlm * 10_000_000)
        
        source_account = soroban_server.load_account(user_public_key)
        
        params = [
            scval.to_uint64(bot_id),
            scval.to_uint64(user_id),
            scval.to_int128(amount_stroops),
        ]
        
        tx = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100000,
            )
            .append_invoke_contract_function_op(
                contract_id=CONTRACT_ID,
                function_name="withdraw",
                parameters=params,
            )
            .set_timeout(300)
            .build()
        )
        
        tx = soroban_server.prepare_transaction(tx)
        
        print(f"[CONTRACT] Withdraw XDR created: {amount_xlm} XLM")
        return tx.to_xdr(), None
        
    except Exception as e:
        print(f"[CONTRACT] Withdraw XDR error: {e}")
        return None, str(e)


def contract_settle_profit(bot_id: int, user_id: int, profit_xlm: float):
    """
    Settle profit - contract sends commission to developer and platform.
    
    Contract'taki hesaplama:
    - total_commission = profit_amount * profit_share_bps / 10000
    - platform_fee = total_commission * platform_cut_bps / 10000
    - dev_fee = total_commission - platform_fee
    
    Örnek: profit=100 XLM, profit_share=30%, platform_cut=10%
    - total_commission = 100 * 3000 / 10000 = 30 XLM
    - platform_fee = 30 * 1000 / 10000 = 3 XLM
    - dev_fee = 30 - 3 = 27 XLM
    """
    profit_stroops = int(profit_xlm * 10_000_000)
    
    if profit_stroops <= 0:
        return None
    
    params = [
        scval.to_uint64(bot_id),
        scval.to_uint64(user_id),
        scval.to_int128(profit_stroops),
    ]
    
    print(f"[CONTRACT] Settling profit: {profit_xlm} XLM (profit amount, not commission)")
    return invoke_contract("settle_profit", params, PLATFORM_SECRET_KEY)


def submit_signed_tx(signed_xdr: str):
    """Submit a signed Soroban transaction"""
    try:
        from stellar_sdk import TransactionEnvelope
        
        tx = TransactionEnvelope.from_xdr(signed_xdr, network_passphrase=NETWORK_PASSPHRASE)
        response = soroban_server.send_transaction(tx)
        
        print(f"[CONTRACT] TX submitted: {response.hash}")
        
        tx_hash = response.hash
        for _ in range(30):
            time.sleep(1)
            result = soroban_server.get_transaction(tx_hash)
            if result.status == GetTransactionStatus.SUCCESS:
                return {"success": True, "hash": tx_hash}
            elif result.status == GetTransactionStatus.FAILED:
                return {"success": False, "error": "Transaction failed"}
        
        return {"success": False, "error": "Timeout"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============== API ENDPOINTS ==============

@app.route('/bots', methods=['GET'])
def get_bots():
    """Return list of available trading bots with commission structure"""
    bots_public = []
    for bot in TRADING_BOTS:
        total_rate = bot['total_commission_rate']  # Developer'ın belirlediği oran (örn: %10)
        platform_cut = bot['platform_cut_percent']  # Sabit %10 (developer'dan kesilir)
        
        # Platform = total_rate * platform_cut / 100
        # Developer net = total_rate - platform
        platform_rate = total_rate * platform_cut / 100
        developer_net_rate = total_rate - platform_rate
        
        bots_public.append({
            "id": bot['id'],
            "name": bot['name'],
            "strategy": bot['strategy'],
            "total_commission_rate": total_rate,       # Toplam kesinti (kullanıcıdan)
            "developer_rate": developer_net_rate,       # Developer'ın net payı
            "platform_rate": platform_rate,             # Platform payı
            "platform_cut_percent": platform_cut,       # Platform kesintisi %10
            "min_commission_deposit": bot['min_commission_deposit'],
            "developer": bot['developer'],
            "platform": bot['platform'],
            "contract_id": CONTRACT_ID,
        })
    return jsonify({"success": True, "bots": bots_public})


@app.route('/status', methods=['GET'])
def get_status():
    """Get user's current status"""
    public_key = request.args.get('public_key')
    
    if not public_key:
        return jsonify({"success": False, "error": "Missing public_key"}), 400
    
    session = get_user_session(public_key)
    
    active_bots_list = []
    for bot_id, bot_data in session['active_bots'].items():
        bot_info = bot_data.copy()
        bot_info['bot_id'] = bot_id
        bot_info['is_accessible'] = bot_data['commission_balance'] > 0
        active_bots_list.append(bot_info)
    
    return jsonify({
        "success": True,
        "user_public_key": public_key,
        "active_bots": active_bots_list
    })


@app.route('/create-deposit-tx', methods=['POST'])
def create_deposit_tx():
    """Create contract deposit transaction for Freighter to sign"""
    try:
        data = request.json
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        amount = float(data.get('amount', 10))
        
        print(f"[DEPOSIT] Creating contract TX: bot={bot_id}, amount={amount} XLM")
        
        if not all([bot_id, user_public_key]):
            return jsonify({"success": False, "error": "Missing parameters"}), 400
        
        bot = next((b for b in TRADING_BOTS if b['id'] == bot_id), None)
        if not bot:
            return jsonify({"success": False, "error": "Bot not found"}), 404
        
        bot_index = get_bot_index(bot_id)
        user_hash = get_user_hash(user_public_key)
        
        # Bot'tan developer ve oranları al
        developer_address = bot['developer']
        total_rate = bot['total_commission_rate']  # Developer'ın belirlediği toplam oran
        platform_cut = bot['platform_cut_percent']  # Sabit %10 platform kesintisi
        
        # Platform developer'dan alıyor
        platform_rate = total_rate * platform_cut / 100
        developer_net_rate = total_rate - platform_rate
        
        # Init vault if needed (ignore errors - might already exist)
        try:
            contract_init_vault(
                bot_id=bot_index,
                user_id=user_hash,
                user_address=user_public_key,
                developer_address=developer_address,
                total_commission_rate=total_rate,
                platform_cut_percent=platform_cut,
            )
        except Exception as e:
            print(f"[INIT_VAULT] Muhtemelen zaten var: {e}")
        
        # Create contract deposit XDR
        xdr, error = contract_deposit(bot_index, user_hash, amount, user_public_key)
        
        if error:
            return jsonify({"success": False, "error": f"Contract error: {error}"}), 400
        
        return jsonify({
            "success": True,
            "xdr": xdr,
            "network_passphrase": NETWORK_PASSPHRASE,
            "contract_id": CONTRACT_ID,
            "developer": developer_address,
            "platform": PLATFORM_PUBLIC_KEY,
            "total_commission_rate": total_rate,
            "developer_rate": developer_net_rate,
            "platform_rate": platform_rate,
        })
        
    except Exception as e:
        print(f"[DEPOSIT] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/submit-transaction', methods=['POST'])
def submit_transaction():
    """Submit a signed contract transaction"""
    try:
        data = request.json
        signed_xdr = data.get('signed_xdr')
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        amount = float(data.get('amount', 10))
        
        print(f"[SUBMIT] bot={bot_id}, amount={amount} XLM")
        
        if not signed_xdr:
            return jsonify({"success": False, "error": "Missing signed_xdr"}), 400
        
        result = submit_signed_tx(signed_xdr)
        
        if not result['success']:
            return jsonify({"success": False, "error": result.get('error')}), 400
        
        tx_hash = result.get('hash', '')
        
        # Update session
        if bot_id and user_public_key:
            session = get_user_session(user_public_key)
            
            if bot_id in session['active_bots']:
                session['active_bots'][bot_id]['commission_balance'] += amount
                session['active_bots'][bot_id]['total_deposited'] += amount
            else:
                session['active_bots'][bot_id] = {
                    "commission_balance": amount,
                    "total_deposited": amount,
                    "total_commission_paid": 0,
                    "simulation_balance": STARTING_SIMULATION_BALANCE,
                    "starting_balance": STARTING_SIMULATION_BALANCE,
                    "total_profit": 0,
                    "high_water_mark": STARTING_SIMULATION_BALANCE,
                    "current_day": 0,
                    "daily_history": [{
                        "day": 0,
                        "performance_percent": 0,
                        "profit_usd": 0,
                        "commission_xlm": 0,
                        "simulation_balance": STARTING_SIMULATION_BALANCE,
                        "commission_balance": amount,
                        "high_water_mark": STARTING_SIMULATION_BALANCE
                    }],
                    "is_accessible": True,
                    "deposit_tx": tx_hash,
                    "contract_id": CONTRACT_ID,
                }
        
        return jsonify({
            "success": True,
            "transaction_hash": tx_hash,
            "explorer_url": f"https://stellar.expert/explorer/testnet/tx/{tx_hash}",
            "contract_id": CONTRACT_ID,
        })
        
    except Exception as e:
        print(f"[SUBMIT] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/simulate-day', methods=['POST'])
def simulate_day():
    """
    Simulate next day's trading
    Komisyon dağılımı (arkadaşın init_vault.py mantığına göre):
    - Developer'a: profit_share_rate % (ör: %30)
    - Platform'a: platform_cut_rate % (ör: %10)
    - Toplam kesinti: %40
    """
    try:
        data = request.json
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        
        if not all([bot_id, user_public_key]):
            return jsonify({"success": False, "error": "Missing parameters"}), 400
        
        session = get_user_session(user_public_key)
        
        if bot_id not in session['active_bots']:
            return jsonify({"success": False, "error": "Not subscribed to this bot"}), 400
        
        bot = next((b for b in TRADING_BOTS if b['id'] == bot_id), None)
        if not bot:
            return jsonify({"success": False, "error": "Bot not found"}), 404
        
        bot_session = session['active_bots'][bot_id]
        
        if bot_session['commission_balance'] <= 0:
            bot_session['is_accessible'] = False
            return jsonify({
                "success": False,
                "error": "Commission balance depleted! Add more to continue.",
                "needs_topup": True
            }), 400
        
        # Generate daily performance
        performance_percent = generate_daily_performance()
        profit_usd = bot_session['simulation_balance'] * (performance_percent / 100)
        new_balance = bot_session['simulation_balance'] + profit_usd
        
        high_water_mark = bot_session.get('high_water_mark', bot_session['starting_balance'])
        
        # Get real-time XLM/USD price
        xlm_usd_rate = get_xlm_usd_price()
        total_commission_xlm = 0
        developer_commission_xlm = 0
        platform_commission_xlm = 0
        
        # Only charge commission on NEW profits above HWM
        if new_balance > high_water_mark:
            taxable_profit = new_balance - high_water_mark
            taxable_profit_xlm = taxable_profit / xlm_usd_rate  # USD → XLM
            
            # Komisyon mantığı:
            # - Toplam komisyon: Kârın %10'u (total_commission_rate)
            # - Platform payı: Toplam komisyonun %10'u (platform_cut_percent)
            # - Developer payı: Toplam komisyon - Platform payı
            # Örnek: $100 kâr → $10 toplam komisyon → $1 platform, $9 developer
            
            total_commission_rate = bot['total_commission_rate']  # %10
            platform_cut_percent = bot['platform_cut_percent']    # %10 of commission
            
            # Toplam komisyonu hesapla
            total_commission_xlm = taxable_profit_xlm * (total_commission_rate / 100)
            
            # Platform developer'ın payından alıyor
            platform_commission_xlm = total_commission_xlm * (platform_cut_percent / 100)
            developer_commission_xlm = total_commission_xlm - platform_commission_xlm
            
            if total_commission_xlm > bot_session['commission_balance']:
                # Oran koruyarak düşür
                ratio = bot_session['commission_balance'] / total_commission_xlm
                taxable_profit_xlm *= ratio
                total_commission_xlm = bot_session['commission_balance']
                platform_commission_xlm = total_commission_xlm * (platform_cut_percent / 100)
                developer_commission_xlm = total_commission_xlm - platform_commission_xlm
            
            bot_session['high_water_mark'] = new_balance
            
            # Call contract to settle profit
            # Contract'a KÂR MİKTARINI gönderiyoruz, contract toplam komisyonu hesaplayıp dağıtacak
            if taxable_profit_xlm > 0.0001:
                bot_index = get_bot_index(bot_id)
                user_hash = get_user_hash(user_public_key)
                contract_settle_profit(bot_index, user_hash, taxable_profit_xlm)
        
        # Update session
        bot_session['simulation_balance'] = new_balance
        bot_session['total_profit'] += profit_usd
        bot_session['commission_balance'] -= total_commission_xlm
        bot_session['total_commission_paid'] += total_commission_xlm
        bot_session['current_day'] += 1
        
        if bot_session['commission_balance'] <= 0:
            bot_session['is_accessible'] = False
        
        bot_session['daily_history'].append({
            "day": bot_session['current_day'],
            "performance_percent": performance_percent,
            "profit_usd": round(profit_usd, 2),
            "commission_xlm": round(total_commission_xlm, 4),
            "developer_xlm": round(developer_commission_xlm, 4),
            "platform_xlm": round(platform_commission_xlm, 4),
            "simulation_balance": round(bot_session['simulation_balance'], 2),
            "commission_balance": round(bot_session['commission_balance'], 4),
            "high_water_mark": round(bot_session['high_water_mark'], 2)
        })
        
        print(f"[SIMULATE] Day {bot_session['current_day']}: {performance_percent}%")
        print(f"  → Developer ({bot['developer'][:16]}...): {developer_commission_xlm:.4f} XLM")
        print(f"  → Platform ({PLATFORM_PUBLIC_KEY[:16]}...): {platform_commission_xlm:.4f} XLM")
        
        return jsonify({
            "success": True,
            "day": bot_session['current_day'],
            "performance_percent": performance_percent,
            "profit_usd": round(profit_usd, 2),
            "commission_xlm": round(total_commission_xlm, 4),
            "developer_xlm": round(developer_commission_xlm, 4),
            "platform_xlm": round(platform_commission_xlm, 4),
            "simulation_balance": round(bot_session['simulation_balance'], 2),
            "commission_balance": round(bot_session['commission_balance'], 4),
            "high_water_mark": round(bot_session['high_water_mark'], 2),
            "total_profit": round(bot_session['total_profit'], 2),
            "total_commission_paid": round(bot_session['total_commission_paid'], 4),
            "is_accessible": bot_session['is_accessible'],
            "commission_to": bot['developer'],
            "contract_id": CONTRACT_ID,
        })
        
    except Exception as e:
        print(f"[SIMULATE] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/withdraw', methods=['POST'])
def withdraw():
    """Create contract withdraw transaction"""
    try:
        data = request.json
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        
        if not all([bot_id, user_public_key]):
            return jsonify({"success": False, "error": "Missing parameters"}), 400
        
        session = get_user_session(user_public_key)
        
        if bot_id not in session['active_bots']:
            return jsonify({"success": False, "error": "Not subscribed"}), 400
        
        bot_session = session['active_bots'][bot_id]
        remaining = bot_session['commission_balance']
        
        if remaining <= 0.0001:
            del session['active_bots'][bot_id]
            return jsonify({
                "success": True,
                "message": "No balance to withdraw",
                "amount_withdrawn": 0,
                "needs_signing": False
            })
        
        # Create contract withdraw XDR
        bot_index = get_bot_index(bot_id)
        user_hash = get_user_hash(user_public_key)
        
        xdr, error = contract_withdraw(bot_index, user_hash, remaining, user_public_key)
        
        if error:
            return jsonify({"success": False, "error": f"Contract error: {error}"}), 400
        
        return jsonify({
            "success": True,
            "xdr": xdr,
            "amount": round(remaining, 4),
            "network_passphrase": NETWORK_PASSPHRASE,
            "contract_id": CONTRACT_ID,
            "needs_signing": True
        })
        
    except Exception as e:
        print(f"[WITHDRAW] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/submit-withdraw', methods=['POST'])
def submit_withdraw():
    """Submit signed withdraw transaction"""
    try:
        data = request.json
        signed_xdr = data.get('signed_xdr')
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        
        if not signed_xdr:
            return jsonify({"success": False, "error": "Missing signed_xdr"}), 400
        
        result = submit_signed_tx(signed_xdr)
        
        if not result['success']:
            return jsonify({"success": False, "error": result.get('error')}), 400
        
        # Remove subscription
        session = get_user_session(user_public_key)
        amount = 0
        if bot_id in session['active_bots']:
            amount = session['active_bots'][bot_id]['commission_balance']
            del session['active_bots'][bot_id]
        
        return jsonify({
            "success": True,
            "amount_withdrawn": round(amount, 4),
            "transaction_hash": result.get('hash', ''),
            "explorer_url": f"https://stellar.expert/explorer/testnet/tx/{result.get('hash', '')}"
        })
        
    except Exception as e:
        print(f"[SUBMIT-WITHDRAW] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/reset-simulation', methods=['POST'])
def reset_simulation():
    """Reset simulation (keeps deposit, resets trading simulation)"""
    try:
        data = request.json
        bot_id = data.get('bot_id')
        user_public_key = data.get('user_public_key')
        
        if not all([bot_id, user_public_key]):
            return jsonify({"success": False, "error": "Missing parameters"}), 400
        
        session = get_user_session(user_public_key)
        
        if bot_id not in session['active_bots']:
            return jsonify({"success": False, "error": "Not subscribed"}), 400
        
        bot_session = session['active_bots'][bot_id]
        original_deposit = bot_session['total_deposited']
        
        session['active_bots'][bot_id] = {
            "commission_balance": original_deposit,
            "total_deposited": original_deposit,
            "total_commission_paid": 0,
            "simulation_balance": STARTING_SIMULATION_BALANCE,
            "starting_balance": STARTING_SIMULATION_BALANCE,
            "total_profit": 0,
            "high_water_mark": STARTING_SIMULATION_BALANCE,
            "current_day": 0,
            "daily_history": [{
                "day": 0,
                "performance_percent": 0,
                "profit_usd": 0,
                "commission_xlm": 0,
                "simulation_balance": STARTING_SIMULATION_BALANCE,
                "commission_balance": original_deposit,
                "high_water_mark": STARTING_SIMULATION_BALANCE
            }],
            "is_accessible": True,
        }
        
        return jsonify({
            "success": True,
            "message": "Simulation reset!",
            "new_commission_balance": original_deposit,
            "new_simulation_balance": STARTING_SIMULATION_BALANCE
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/topup', methods=['POST'])
def topup():
    """Create topup transaction (same as deposit)"""
    return create_deposit_tx()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "network": "stellar-testnet",
        "contract_id": CONTRACT_ID,
        "developer": DEVELOPER_PUBLIC_KEY,
    })


@app.route('/contract-info', methods=['GET'])
def contract_info():
    """Get contract information"""
    return jsonify({
        "success": True,
        "contract_id": CONTRACT_ID,
        "developer_wallet": DEVELOPER_PUBLIC_KEY,
        "native_asset": NATIVE_ASSET_ID,
        "network": "testnet",
        "explorer": f"https://stellar.expert/explorer/testnet/contract/{CONTRACT_ID}"
    })


if __name__ == '__main__':
    print("=" * 60)
    print("🐋 Whaleer.com Demo - Profit Sharing via Smart Contract")
    print("=" * 60)
    print(f"Contract ID: {CONTRACT_ID}")
    print(f"Developer:   {DEVELOPER_PUBLIC_KEY}")
    print(f"Native XLM:  {NATIVE_ASSET_ID}")
    print()
    print("All deposits/withdraws go through Soroban Smart Contract")
    print("Commissions are automatically sent to developer wallet")
    print("=" * 60)
    print()
    
    app.run(host='127.0.0.1', port=5328, debug=True)
