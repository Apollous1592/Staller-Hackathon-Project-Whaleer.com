# 🐋 Whaleer Profit-Sharing Protocol

### On-Chain Profit Sharing for Trading Bots Using 3-Wallet Revenue Split + High-Water Mark Fee Model
### Powered by Stellar Soroban Smart Contracts

---

## 🚀 1. Overview

Trading bots generate millions in profits every day — but developers, platforms, and users lack a fair, automated, and transparent revenue-sharing mechanism.

**Current ecosystem problems:**
- ❌ No automated profit commissions
- ❌ No transparent developer/platform revenue split
- ❌ No on-chain settlement
- ❌ No High-Water Mark logic
- ❌ Platforms must trust centralized systems

**Whaleer Profit-Sharing Protocol solves this.**

### ✅ What This Protocol Enables
- 3-way automated commission distribution
- High-Water Mark (HWM) based performance fee
- Fully on-chain deposit / withdraw
- Freighter-based non-custodial signing
- Automated fee distribution via Soroban Smart Contracts

---

## 🧩 2. System Architecture

### 2.1 Three-Wallet Revenue Model

```
                   ┌────────────────────────┐
                   │     Platform Wallet    │
                   │    (platform revenue)  │
                   └────────────▲───────────┘
                                │ 10% of Commission
                                │
                   ┌────────────┴───────────┐
                   │ Soroban Smart Contract │
                   │  (auto-fee settlement) │
                   └────────────▲───────────┘
                                │ 90% of Commission
                                │
          ┌─────────────────────┴─────────────────────┐
          │                                           │
┌─────────┴──────────┐                     ┌─────────┴──────────┐
│     User Wallet     │                     │  Developer Wallet  │
│ (commission deposit)│                     │   (revenue share)  │
└─────────────────────┘                     └────────────────────┘
```

### 2.2 Full System Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S BROWSER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Next.js Frontend (React)                         │    │
│  │  • Wallet Connection (Freighter)                                     │    │
│  │  • Bot Selection & Deposit                                           │    │
│  │  • Daily Simulation & Receipts                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ XDR Transaction
                                      ▼
                              ┌───────────────┐
                              │   Freighter   │
                              │ (User Signs)  │
                              └───────┬───────┘
                                      │ Signed XDR
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND SERVER                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Python Flask API (Port 5328)                      │    │
│  │  • XDR Transaction Building                                          │    │
│  │  • Real-time XLM Price (CoinGecko)                                   │    │
│  │  • High-Water Mark Tracking                                          │    │
│  │  • Commission Calculation                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Soroban RPC
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        STELLAR BLOCKCHAIN (Testnet)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Soroban Smart Contract                            │    │
│  │  • init_vault: Create user vault with commission rates               │    │
│  │  • deposit: Lock XLM as commission reserve                           │    │
│  │  • settle_profit: Distribute commission to dev + platform            │    │
│  │  • withdraw: Return remaining balance to user                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Contract ID: CBEZLTP6IW3KETVKHHQIZP6MV4N5ROD3O2YMXE3WPDBHWYO53UBDJDFI      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📈 3. High-Water Mark (HWM)

A hedge-fund-grade performance fee model ensuring fairness.

### Why HWM?
- User pays fees **only** on new profits
- Losses reset fee eligibility
- Prevents double-charging

### Example

```
Start:  $100 → HWM = $100
Day 1:  $120 → Fee on +$20  → HWM = $120
Day 2:  $90  → No fee       → HWM = $120 (unchanged)
Day 3:  $130 → Fee on +$10  → HWM = $130 (only new profit above $120)
```

```
                    Balance
        $130 ─ ─ ─ ─ ─ ─ ─ ─●─ ─ ─ ─ HWM Updated
                          ╱
        $120 ─ ─ ─●─ ─ ─ ╱─ ─ ─ ─ ─ HWM
                 ╱     ╱
        $100 ───●     ╱
                 ╲   ╱
         $90 ─ ─ ─●─ ─ ─ ─ ─ ─ ─ ─ No Fee (below HWM)
              
             Day1  Day2  Day3
```

---

## 💰 4. Commission Model

### Stakeholder Split

| Party | Description | Commission Share |
|-------|-------------|------------------|
| **Developer** | Bot creator, sets rate | 90% of commission |
| **Platform** | Protocol operator | 10% of commission |
| **User** | Pays from profits only | — |

### Example: Developer Sets 10% Rate

```
User Profit: $100
     │
     ▼
Total Commission: $10 (10% of profit)
     │
     ├──► Developer: $9 (90% of $10)
     │
     └──► Platform: $1 (10% of $10)
```

### Soroban BPS Conversion

Backend converts percentages to Soroban Basis Points (BPS):

```python
profit_share_bps = total_commission_rate * 100   # 10% → 1000
platform_cut_bps = platform_cut_percent * 100    # 10% → 1000
```

Contract calculation:
```rust
total_commission = profit * profit_share_bps / 10000;
platform_fee = total_commission * platform_cut_bps / 10000;
developer_fee = total_commission - platform_fee;
```

---

## 🔒 5. Soroban Contract Functions

| Function | Description | Signer |
|----------|-------------|--------|
| `init_vault` | Creates storage for user-bot pair | Platform (backend) |
| `deposit` | User funds fee reserve | User (Freighter) |
| `withdraw` | User withdraws remaining fees | User (Freighter) |
| `settle_profit` | Distributes fee to dev + platform | Platform (backend) |

### XDR Signing Flow

```
1. Backend creates unsigned XDR
          ↓
2. Frontend sends XDR to Freighter
          ↓
3. User signs locally (non-custodial)
          ↓
4. Signed XDR sent back to backend
          ↓
5. Backend submits to Soroban
          ↓
6. Smart contract executes fee logic
```

---

## 🧠 6. Backend Architecture

### Key Responsibilities
- Create XDR transactions
- Manage High-Water Mark logic
- Simulate trading profits
- Trigger settlement calls
- Track user state
- Handle deposit/withdraw flows

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/bots` | GET | List available trading bots |
| `/status` | GET | Get user's current status |
| `/create-deposit-tx` | POST | Create deposit XDR for signing |
| `/submit-transaction` | POST | Submit signed transaction |
| `/simulate-day` | POST | Simulate daily trading |
| `/create-withdraw-tx` | POST | Create withdraw XDR |
| `/submit-withdraw` | POST | Submit signed withdrawal |

---

## 📊 7. Trading Simulation Engine

Features:
- Daily return between **−3% to +5%**
- Full HWM logic implementation
- Automatic fee deduction
- Soroban settlement calls on profit
- Fee depletion disables bot usage
- Daily historical log with receipts

---

## 🛠 8. Installation & Running

### Prerequisites
- Node.js v18+
- Python 3.9+
- [Freighter Wallet](https://freighter.app/) browser extension

### Backend Setup

```bash
cd api
pip install -r requirements.txt
python index.py
# Runs on http://127.0.0.1:5328
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:3000
```

### Using the Demo

1. **Connect Wallet** → Click "Connect Freighter" (Stellar Testnet)
2. **Select Bot** → Choose a trading bot to follow
3. **Deposit** → Deposit XLM as commission reserve
4. **Simulate** → Click "Simulate Day" to see daily P&L
5. **Watch** → See commission distributed in real-time
6. **Withdraw** → Take back remaining balance anytime

---

## 📁 9. Project Structure

```
├── frontend/                 # Next.js React Application
│   ├── app/
│   │   ├── page.tsx         # Main UI component
│   │   ├── layout.tsx       # App layout
│   │   └── globals.css      # Styles
│   ├── package.json
│   └── next.config.js       # API proxy config
│
├── api/                      # Python Flask Backend
│   ├── index.py             # Main API + Stellar integration
│   └── requirements.txt     # Python dependencies
│
├── stellar-rs/              # Soroban Smart Contract (Rust)
│   ├── src/lib.rs          # Contract logic
│   └── Cargo.toml          # Rust dependencies
│
└── README.md
```

---

## 🔐 10. Security

- ✅ **Non-custodial signing** — User keys never leave Freighter
- ✅ **No developer private key stored** — Backend only holds platform admin key
- ✅ **On-chain transparency** — All transactions auditable
- ✅ **Immutable fee flows** — Smart contract enforces rules

⚠️ **TESTNET DEMO** — This uses Stellar Testnet, no real funds involved.

---

## 🏆 11. Why This Project Stands Out

### Innovation
- **First 3-party revenue model on Soroban**
- On-chain performance fee settlement
- High-Water Mark implemented in smart contracts

### Technical Depth
- Custom XDR generation pipeline
- Full contract invocation flow
- State management + fee reserve
- Multi-wallet commission distribution
- Real-time XLM/USD price integration

### Real-World Value
- Bot marketplaces can adopt instantly
- Developers monetize performance fairly
- Platforms earn transparent revenue
- Users pay only on actual profits

---

## 🌐 12. Links

- **Whaleer.com**: [https://whaleer.com](https://whaleer.com)
- **Stellar**: [https://stellar.org](https://stellar.org)
- **Soroban Docs**: [https://soroban.stellar.org](https://soroban.stellar.org)
- **Freighter Wallet**: [https://freighter.app](https://freighter.app)

---

## 📝 License

MIT License — Built for Stellar Hackathon 2025

---

<p align="center">
  <b>🐋 Whaleer — Follow the Whales, Share the Profits 🐋</b>
</p>
