#![no_std]
use soroban_sdk::{contract, contractimpl, contracttype, Address, Env, Symbol, token, symbol_short};

// --- VERİ YAPILARI ---

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    Admin,                  
    Vault(u64, u64),        // (BotID, UserID) -> VaultObj
}

#[contracttype]
#[derive(Clone)]
pub struct VaultObj {
    pub user_address: Address, // Değiştirilebilir
    pub developer: Address,    // Değiştirilebilir
    pub platform: Address,     
    pub asset: Address,        
    pub profit_share_bps: u32, 
    pub platform_cut_bps: u32, 
    pub balance: i128,         
    pub is_active: bool,       
}

// --- OLAYLAR (EVENTS) ---
const EVT_DEPOSIT: Symbol = symbol_short!("deposit");
const EVT_WITHDRAW: Symbol = symbol_short!("withdraw");
const EVT_SETTLED: Symbol = symbol_short!("settled");
const EVT_INSUFF: Symbol = symbol_short!("insuff"); 
// YENİ EVENTLER
const EVT_UPD_USER: Symbol = symbol_short!("upd_user");
const EVT_UPD_DEV: Symbol = symbol_short!("upd_dev");

#[contract]
pub struct ProfitSharingVault;

#[contractimpl]
impl ProfitSharingVault {

    // 1. INIT
    pub fn init(env: Env, admin: Address) {
        if env.storage().instance().has(&DataKey::Admin) {
            panic!("Already initialized");
        }
        env.storage().instance().set(&DataKey::Admin, &admin);
    }

    // 2. INIT_VAULT
    pub fn init_vault(
        env: Env,
        bot_id: u64,
        user_id: u64,          
        user_address: Address, 
        developer: Address,
        platform: Address,
        asset: Address,
        profit_share_bps: u32,
        platform_cut_bps: u32
    ) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).expect("Not initialized");
        admin.require_auth(); 

        if profit_share_bps > 10_000 { panic!("Invalid profit_share_bps"); }
        if platform_cut_bps > 10_000 { panic!("Invalid platform_cut_bps"); }

        let key = DataKey::Vault(bot_id, user_id);
        
        if env.storage().persistent().has(&key) {
            panic!("Vault already exists");
        }
        
        let new_vault = VaultObj {
            user_address, 
            developer,
            platform,
            asset,
            profit_share_bps,
            platform_cut_bps,
            balance: 0,
            is_active: true,
        };

        env.storage().persistent().set(&key, &new_vault);
    }

    // 3. DEPOSIT
    pub fn deposit(env: Env, bot_id: u64, user_id: u64, amount: i128) {
        if amount <= 0 { panic!("Amount must be positive"); }

        let key = DataKey::Vault(bot_id, user_id);
        let mut vault: VaultObj = env.storage().persistent().get(&key).expect("Vault not found");

        // İmzalayan kişi, ŞU ANKİ kayıtlı cüzdan olmalı
        vault.user_address.require_auth();

        let client = token::Client::new(&env, &vault.asset);
        client.transfer(&vault.user_address, &env.current_contract_address(), &amount);

        vault.balance += amount;
        vault.is_active = true; 
        
        env.storage().persistent().set(&key, &vault);

        env.events().publish((EVT_DEPOSIT, user_id), (bot_id, amount));
    }

    // 4. WITHDRAW
    pub fn withdraw(env: Env, bot_id: u64, user_id: u64, amount: i128) {
        if amount <= 0 { panic!("Amount must be positive"); }

        let key = DataKey::Vault(bot_id, user_id);
        let mut vault: VaultObj = env.storage().persistent().get(&key).expect("Vault not found");

        vault.user_address.require_auth();

        if amount > vault.balance {
            panic!("Insufficient vault balance");
        }

        let client = token::Client::new(&env, &vault.asset);
        client.transfer(&env.current_contract_address(), &vault.user_address, &amount);

        vault.balance -= amount;
        env.storage().persistent().set(&key, &vault);

        env.events().publish((EVT_WITHDRAW, user_id), (bot_id, amount));
    }

    // 5. SETTLE_PROFIT
    pub fn settle_profit(env: Env, bot_id: u64, user_id: u64, profit_amount: i128) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).expect("Not initialized");
        admin.require_auth(); 

        if profit_amount <= 0 { panic!("Profit amount must be positive"); }

        let key = DataKey::Vault(bot_id, user_id);
        let mut vault: VaultObj = env.storage().persistent().get(&key).expect("Vault not found");

        if !vault.is_active { return; }

        let total_commission = (profit_amount * vault.profit_share_bps as i128) / 10_000;

        if vault.balance < total_commission {
            env.events().publish((EVT_INSUFF, user_id), (bot_id, total_commission, vault.balance));
            
            vault.is_active = false;
            env.storage().persistent().set(&key, &vault);
            return;
        }

        let platform_fee = (total_commission * vault.platform_cut_bps as i128) / 10_000;
        let dev_fee = total_commission - platform_fee;

        let client = token::Client::new(&env, &vault.asset);

        if platform_fee > 0 {
            client.transfer(&env.current_contract_address(), &vault.platform, &platform_fee);
        }

        if dev_fee > 0 {
            client.transfer(&env.current_contract_address(), &vault.developer, &dev_fee);
        }

        vault.balance -= total_commission;
        env.storage().persistent().set(&key, &vault);

        env.events().publish((EVT_SETTLED, user_id), (bot_id, profit_amount, total_commission));
    }

    // 6. GET_VAULT
    pub fn get_vault(env: Env, bot_id: u64, user_id: u64) -> VaultObj {
        let key = DataKey::Vault(bot_id, user_id);
        env.storage().persistent().get(&key).expect("Vault not found")
    }

    // 7. UPDATE_USER_ADDRESS: Kullanıcı cüzdanını değiştirir
    pub fn update_user_address(env: Env, bot_id: u64, user_id: u64, new_address: Address) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).expect("Not initialized");
        admin.require_auth(); // Sadece Admin değiştirebilir (DB Sync için)

        let key = DataKey::Vault(bot_id, user_id);
        let mut vault: VaultObj = env.storage().persistent().get(&key).expect("Vault not found");

        vault.user_address = new_address.clone();
        env.storage().persistent().set(&key, &vault);

        // Event: (Topic: upd_user, Data: new_address)
        env.events().publish((EVT_UPD_USER, user_id), (bot_id, new_address));
    }

    // 8. UPDATE_DEVELOPER_ADDRESS: Geliştirici cüzdanını değiştirir
    pub fn update_developer_address(env: Env, bot_id: u64, user_id: u64, new_address: Address) {
        let admin: Address = env.storage().instance().get(&DataKey::Admin).expect("Not initialized");
        admin.require_auth(); // Sadece Admin değiştirebilir

        let key = DataKey::Vault(bot_id, user_id);
        let mut vault: VaultObj = env.storage().persistent().get(&key).expect("Vault not found");

        vault.developer = new_address.clone();
        env.storage().persistent().set(&key, &vault);

        env.events().publish((EVT_UPD_DEV, user_id), (bot_id, new_address));
    }
}