import os
from decimal import Decimal

from stellar_sdk import (
    Keypair,
    TransactionBuilder,
    Network,
    SorobanServer,
    Server,
    scval
)

# ENV
# Not: Transaction oluştururken Sequence Number almak için Horizon URL gereklidir.
HORIZON_URL = os.getenv("STELLAR_HORIZON_URL", "https://horizon-testnet.stellar.org")
RPC_URL = os.getenv("STELLAR_RPC_URL", "https://soroban-testnet.stellar.org")
NETWORK_PASSPHRASE = os.getenv("STELLAR_NETWORK_PASSPHRASE", "Test SDF Network ; September 2015")

VAULT_CONTRACT_ID = os.getenv("WHALEER_VAULT_CONTRACT_ID")
ADMIN_SECRET = os.getenv("WHALEER_ADMIN_SECRET_KEY")
ADMIN_PUBLIC = os.getenv("WHALEER_ADMIN_PUBLIC_KEY")
ASSET_CONTRACT = os.getenv("NATIVE_TOKEN_CONTRACT_ID")  # Native XLM Contract ID

# Sunucuları Başlat
soroban_server = SorobanServer(RPC_URL)
horizon_server = Server(HORIZON_URL)

def init_vault_on_chain(
    bot_id: int,
    user_id: int,
    user_address: str,
    developer_address: str,
    profit_share_rate: Decimal | float | int,
    platform_cut_rate: Decimal | float | int = 10,
):
    """
    Soroban kontratındaki init_vault fonksiyonunu çağırır.
    Not: stellar-sdk standart metotları senkrondur, bu yüzden async kullanıyorsan
    bu fonksiyonu bir thread pool içinde çağırmak performans için daha iyidir.
    """
    print("Bot id:", bot_id)
    print("User id:", user_id)
    print("User address:", user_address)
    print("Developer address:", developer_address)
    print("Platform address:", ADMIN_PUBLIC)
    print("Profit share rate:", profit_share_rate)
    print("Platform cut rate:", platform_cut_rate)

    if not (VAULT_CONTRACT_ID and ADMIN_SECRET and ASSET_CONTRACT):
        raise RuntimeError("Vault contract ENV'leri eksik.")
#
    # % → bps (ör: 15 → 1500)
    profit_bps = int(Decimal(str(profit_share_rate)) * 100)
    platform_bps = int(Decimal(str(platform_cut_rate)) * 100)
#
    if profit_bps < 0 or platform_bps < 0:
        raise ValueError("Profit share ve platform cut negatif olamaz.")
    if profit_bps > 10_000 or platform_bps > 10_000:
        raise ValueError("Oranlar %100 (10000 bps) üzerinde olamaz.")
#
    # Admin Keypair
    admin_kp = Keypair.from_secret(ADMIN_SECRET)
#
    # 1. Kaynak Hesabı Yükle (Horizon'dan Sequence Number Alınır)
    try:
        source_account = horizon_server.load_account(admin_kp.public_key)
    except Exception as e:
        raise RuntimeError(f"Admin hesabı yüklenemedi (Horizon hatası): {e}")
#
    # 2. Argümanları Hazırla (scval kullanarak)
    # fn init_vault(env, bot_id, user_id, user_address, developer, platform, asset, profit_share_bps, platform_cut_bps)
    args = [
        scval.to_uint64(bot_id),
        scval.to_uint64(user_id),
        scval.to_address(user_address),
        scval.to_address(developer_address),
        scval.to_address(ADMIN_PUBLIC), 
        scval.to_address(ASSET_CONTRACT),
        scval.to_uint32(profit_bps),
        scval.to_uint32(platform_bps),
    ]
#
    # 3. İşlemi Oluştur (TransactionBuilder)
    tx = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=NETWORK_PASSPHRASE,
            base_fee=100, # Simülasyon sonrası artabilir
        )
        .set_timeout(30)
        .append_invoke_contract_function_op(
            contract_id=VAULT_CONTRACT_ID,
            function_name="init_vault",
            parameters=args,
        )
        .build()
    )
#
    print("⏳ Simülasyon yapılıyor...")
    sim_resp = soroban_server.simulate_transaction(tx)
    print(f"🔵 Simülasyon yanıtı: {sim_resp}")
    # --- HATA DETAYLANDIRMA (YENİ) ---
    if "error" in sim_resp:
        error_msg = sim_resp['error']
        print(f"🔴 Simulation Error: {error_msg}")
        # Eğer event loglarında panic mesajı varsa onu bulmaya çalışalım
        events = sim_resp.get('events', [])
        for evt in events:
            print(f"⚠️ Simulation Event: {evt}")
        
        # Genelde hata detayı 'resultError' veya string içinde gizlidir
        print(f"🔴 TAM SİMÜLASYON YANITI: {sim_resp}")
        
        raise RuntimeError(f"Simülasyon Başarısız: {error_msg}")
    
    # Sonuçların içinde hata var mı?
    if "results" in sim_resp:
        for res in sim_resp["results"]:
            if "error" in res:
                print(f"🔴 Result Error: {res}")
                raise RuntimeError(f"Simülasyon Sonuç Hatası: {res['error']}")
#
    # Simülasyon verilerini (footprint/auth) işleme ekle
    # Not: Bazı SDK sürümlerinde bu metodun adı farklı olabilir, standart: prepare_transaction
    tx = soroban_server.prepare_transaction(tx, sim_resp)
#
    # 5. İmzala
    tx.sign(admin_kp)
#
    # 6. Gönder
    print("🚀 İşlem ağa gönderiliyor...")
    send_resp = soroban_server.send_transaction(tx)
#
    if send_resp.status == "ERROR":
        raise RuntimeError(f"Transaction Failed: {send_resp}")
#
    # Hash döndür
    return send_resp.hash