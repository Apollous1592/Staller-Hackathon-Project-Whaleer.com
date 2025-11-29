'use client';

import { useState, useEffect } from 'react';
import { isConnected, requestAccess, getAddress, signTransaction, getNetwork } from '@stellar/freighter-api';

interface Bot {
  id: string;
  name: string;
  strategy: string;
  commission_rate: number;
  developer_rate: number;
  platform_rate: number;
  total_commission: number;
  min_commission_deposit: number;
  deposit_address: string;
  whale_address: string;
  developer: string;
  platform: string;
  contract_id: string;
}

interface DailyRecord {
  day: number;
  performance_percent: number;
  profit_usd: number;
  commission_xlm: number;
  developer_xlm?: number;
  platform_xlm?: number;
  simulation_balance: number;
  commission_balance: number;
  high_water_mark?: number;  // HWM at that point
}

interface ActiveBot {
  bot_id: string;
  commission_balance: number;    // Real XLM for commissions
  total_deposited: number;
  total_commission_paid: number;
  simulation_balance: number;    // Virtual $ balance
  starting_balance: number;
  total_profit: number;
  high_water_mark: number;       // Highest balance ever reached
  current_day: number;
  daily_history: DailyRecord[];
  is_accessible: boolean;
  deposit_tx?: string;
}

interface UserStatus {
  user_public_key: string;
  active_bots: ActiveBot[];
}

interface WalletState {
  isConnected: boolean;
  publicKey: string | null;
  network: string | null;
}

// Stellar Testnet Configuration
const STELLAR_NETWORK = 'TESTNET';
const HORIZON_URL = 'https://horizon-testnet.stellar.org';
const NETWORK_PASSPHRASE = 'Test SDF Network ; September 2015';

export default function Home() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [userStatus, setUserStatus] = useState<UserStatus | null>(null);
  const [wallet, setWallet] = useState<WalletState>({
    isConnected: false,
    publicKey: null,
    network: null,
  });
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null);
  const [showDepositModal, setShowDepositModal] = useState(false);
  const [showTopupModal, setShowTopupModal] = useState(false);
  const [depositAmount, setDepositAmount] = useState('10');
  const [topupAmount, setTopupAmount] = useState('5');
  const [freighterInstalled, setFreighterInstalled] = useState<boolean | null>(null);
  const [xlmBalance, setXlmBalance] = useState<string | null>(null);
  const [expandedBot, setExpandedBot] = useState<string | null>(null);

  // Check if Freighter is installed
  useEffect(() => {
    const checkFreighter = async () => {
      for (let i = 0; i < 5; i++) {
        await new Promise(resolve => setTimeout(resolve, 500));
        try {
          const connectionResult = await isConnected();
          if (connectionResult && typeof connectionResult.isConnected !== 'undefined') {
            setFreighterInstalled(true);
            if (connectionResult.isConnected) {
              const addressResult = await getAddress();
              const networkResult = await getNetwork();
              if (addressResult.address && !addressResult.error) {
                setWallet({ 
                  isConnected: true, 
                  publicKey: addressResult.address, 
                  network: networkResult.network || null 
                });
              }
            }
            return;
          }
        } catch (e) {
          console.log('Freighter check attempt', i + 1, e);
        }
      }
      setFreighterInstalled(false);
    };
    
    checkFreighter();
  }, []);

  useEffect(() => {
    fetchBots();
  }, []);

  useEffect(() => {
    if (wallet.isConnected && wallet.publicKey) {
      fetchUserStatus();
      checkAccountBalance();
    }
  }, [wallet.isConnected, wallet.publicKey]);

  const fetchBots = async () => {
    try {
      const res = await fetch('/api/bots');
      const data = await res.json();
      setBots(data.bots || []);
    } catch {
      setMessage({ type: 'error', text: 'Backend connection failed. Make sure it\'s running on port 5328.' });
    } finally {
      setLoading(false);
    }
  };

  const fetchUserStatus = async () => {
    if (!wallet.publicKey) return;
    
    try {
      const res = await fetch(`/api/status?public_key=${encodeURIComponent(wallet.publicKey)}`);
      const data = await res.json();
      if (data.success) {
        setUserStatus(data);
      }
    } catch (error) {
      console.error('Status fetch failed:', error);
    }
  };

  const checkAccountBalance = async () => {
    if (!wallet.publicKey) return;
    
    try {
      const res = await fetch(`${HORIZON_URL}/accounts/${wallet.publicKey}`);
      if (res.ok) {
        const data = await res.json();
        const balance = data.balances.find((b: { asset_type: string }) => b.asset_type === 'native');
        setXlmBalance(parseFloat(balance?.balance || '0').toFixed(2));
      } else if (res.status === 404) {
        setXlmBalance('0 (Unfunded)');
        setMessage({ 
          type: 'warning', 
          text: 'Account not funded! Get free testnet XLM from Stellar Laboratory.' 
        });
      }
    } catch (error) {
      console.error('Balance check failed:', error);
    }
  };

  const connectWallet = async () => {
    if (!freighterInstalled) {
      setMessage({ type: 'error', text: 'Freighter wallet not found. Please install it first.' });
      return;
    }

    setActionLoading('connect');
    setMessage(null);

    try {
      const accessResult = await requestAccess();
      
      if (accessResult.error) {
        throw new Error(accessResult.error);
      }
      
      const pubKey = accessResult.address;
      const networkResult = await getNetwork();
      const network = networkResult.network || 'UNKNOWN';
      
      if (network !== STELLAR_NETWORK) {
        setMessage({ 
          type: 'warning', 
          text: `Please switch to TESTNET in Freighter. Current: ${network}` 
        });
      }
      
      setWallet({ isConnected: true, publicKey: pubKey, network });
      setMessage({ type: 'success', text: `Connected: ${pubKey.substring(0, 8)}...${pubKey.slice(-8)}` });
      
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Connection failed';
      setMessage({ type: 'error', text: errorMessage });
    } finally {
      setActionLoading(null);
    }
  };

  const disconnectWallet = () => {
    setWallet({ isConnected: false, publicKey: null, network: null });
    setUserStatus(null);
    setXlmBalance(null);
    setMessage({ type: 'info', text: 'Wallet disconnected' });
  };

  const openDepositModal = (bot: Bot) => {
    if (!wallet.isConnected) {
      setMessage({ type: 'warning', text: 'Please connect your wallet first' });
      return;
    }
    setSelectedBot(bot);
    setDepositAmount(bot.min_commission_deposit.toString());
    setShowDepositModal(true);
  };

  const openTopupModal = (bot: Bot) => {
    setSelectedBot(bot);
    setTopupAmount('5');
    setShowTopupModal(true);
  };

  const handleDeposit = async () => {
    if (!selectedBot || !wallet.publicKey || !freighterInstalled) return;
    
    setActionLoading('deposit');
    setMessage(null);
    
    try {
      const res = await fetch('/api/create-deposit-tx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: selectedBot.id,
          user_public_key: wallet.publicKey,
          amount: depositAmount,
        }),
      });
      
      const data = await res.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Failed to create transaction');
      }
      
      setMessage({ type: 'info', text: 'Please sign the transaction in Freighter...' });
      
      const signResult = await signTransaction(data.xdr, {
        networkPassphrase: NETWORK_PASSPHRASE,
      });
      
      if (signResult.error) {
        throw new Error(signResult.error);
      }
      
      const signedXdr = signResult.signedTxXdr;
      
      const submitRes = await fetch('/api/submit-transaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signed_xdr: signedXdr,
          bot_id: selectedBot.id,
          user_public_key: wallet.publicKey,
          amount: depositAmount,
          is_topup: false,
          is_contract: data.is_contract || false,
        }),
      });
      
      const submitData = await submitRes.json();
      
      if (submitData.success) {
        const contractText = submitData.is_contract ? ' (via Smart Contract)' : '';
        setMessage({ 
          type: 'success', 
          text: `${depositAmount} XLM commission deposited${contractText}! $1000 simulation started.` 
        });
        setShowDepositModal(false);
        fetchUserStatus();
        checkAccountBalance();
      } else {
        throw new Error(submitData.error || 'Failed to submit transaction');
      }
      
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Deposit failed';
      if (errorMessage.includes('User declined')) {
        setMessage({ type: 'warning', text: 'Transaction cancelled' });
      } else {
        setMessage({ type: 'error', text: errorMessage });
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handleTopup = async () => {
    if (!selectedBot || !wallet.publicKey || !freighterInstalled) return;
    
    setActionLoading('topup');
    setMessage(null);
    
    try {
      const res = await fetch('/api/topup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: selectedBot.id,
          user_public_key: wallet.publicKey,
          amount: topupAmount,
        }),
      });
      
      const data = await res.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Failed to create transaction');
      }
      
      setMessage({ type: 'info', text: 'Please sign the transaction in Freighter...' });
      
      const signResult = await signTransaction(data.xdr, {
        networkPassphrase: NETWORK_PASSPHRASE,
      });
      
      if (signResult.error) {
        throw new Error(signResult.error);
      }
      
      const signedXdr = signResult.signedTxXdr;
      
      const submitRes = await fetch('/api/submit-transaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signed_xdr: signedXdr,
          bot_id: selectedBot.id,
          user_public_key: wallet.publicKey,
          amount: topupAmount,
          is_topup: true,
        }),
      });
      
      const submitData = await submitRes.json();
      
      if (submitData.success) {
        setMessage({ 
          type: 'success', 
          text: `+${topupAmount} XLM commission balance added!` 
        });
        setShowTopupModal(false);
        fetchUserStatus();
        checkAccountBalance();
      } else {
        throw new Error(submitData.error || 'Failed to submit transaction');
      }
      
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Top-up failed';
      if (errorMessage.includes('User declined')) {
        setMessage({ type: 'warning', text: 'Transaction cancelled' });
      } else {
        setMessage({ type: 'error', text: errorMessage });
      }
    } finally {
      setActionLoading(null);
    }
  };

  // Contract Deposit - deposits directly to smart contract
  const handleContractDeposit = async (botId: string, amount: number) => {
    if (!wallet.publicKey || !freighterInstalled) return;
    
    setActionLoading(`contract-deposit-${botId}`);
    setMessage(null);
    
    try {
      // Step 1: Create contract deposit XDR
      const res = await fetch('/api/contract/create-deposit-tx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          user_public_key: wallet.publicKey,
          amount: amount,
        }),
      });
      
      const data = await res.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Failed to create contract transaction');
      }
      
      setMessage({ type: 'info', text: '🔗 Please sign the CONTRACT transaction in Freighter...' });
      
      // Step 2: Sign with Freighter
      const signResult = await signTransaction(data.xdr, {
        networkPassphrase: NETWORK_PASSPHRASE,
      });
      
      if (signResult.error) {
        throw new Error(signResult.error);
      }
      
      // Step 3: Submit signed transaction
      const submitRes = await fetch('/api/contract/submit-deposit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signed_xdr: signResult.signedTxXdr,
          bot_id: botId,
          user_public_key: wallet.publicKey,
          amount: amount,
        }),
      });
      
      const submitData = await submitRes.json();
      
      if (submitData.success) {
        setMessage({ 
          type: 'success', 
          text: `🔗 Contract deposit successful! ${amount} XLM deposited to smart contract` 
        });
        fetchUserStatus();
        checkAccountBalance();
      } else {
        throw new Error(submitData.error || 'Contract deposit failed');
      }
      
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Contract deposit failed';
      if (errorMessage.includes('User declined')) {
        setMessage({ type: 'warning', text: 'Transaction cancelled' });
      } else {
        setMessage({ type: 'error', text: errorMessage });
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handleSimulateDay = async (botId: string) => {
    if (!wallet.publicKey) return;
    
    setActionLoading(`simulate-${botId}`);
    setMessage(null);
    
    try {
      const res = await fetch('/api/simulate-day', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          user_public_key: wallet.publicKey,
        }),
      });
      
      const data = await res.json();
      
      if (data.success) {
        const sign = data.performance_percent >= 0 ? '+' : '';
        const profitSign = data.profit_usd >= 0 ? '+' : '';
        setMessage({ 
          type: data.performance_percent >= 0 ? 'success' : 'warning', 
          text: `Day ${data.day}: ${sign}${data.performance_percent}% | Profit: ${profitSign}$${data.profit_usd.toFixed(2)} | Commission: ${data.commission_xlm.toFixed(4)} XLM` 
        });
        fetchUserStatus();
        checkAccountBalance();
      } else {
        if (data.needs_topup) {
          setMessage({ type: 'error', text: 'Commission balance depleted! Add more to continue.' });
        } else {
          setMessage({ type: 'error', text: data.error || 'Simulation failed' });
        }
      }
    } catch {
      setMessage({ type: 'error', text: 'Simulation failed' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleReset = async (botId: string) => {
    if (!wallet.publicKey) return;
    
    setActionLoading(`reset-${botId}`);
    setMessage(null);
    
    try {
      const res = await fetch('/api/reset-simulation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          user_public_key: wallet.publicKey,
        }),
      });
      
      const data = await res.json();
      
      if (data.success) {
        setMessage({ 
          type: 'success', 
          text: `Reset complete! ${data.refunded_amount.toFixed(4)} XLM commission refunded.`
        });
        fetchUserStatus();
        checkAccountBalance();
      } else {
        setMessage({ type: 'error', text: data.error || 'Reset failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Reset failed' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleWithdraw = async (botId: string) => {
    if (!wallet.publicKey) return;
    
    setActionLoading(`withdraw-${botId}`);
    setMessage(null);
    
    try {
      // Step 1: Request withdraw from backend
      const res = await fetch('/api/withdraw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_id: botId,
          user_public_key: wallet.publicKey,
        }),
      });
      
      const data = await res.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Failed to withdraw');
      }
      
      // Check if withdraw was already processed (no signing needed)
      if (data.needs_signing === false) {
        // Backend already sent the XLM
        if (data.amount_withdrawn > 0) {
          setMessage({ 
            type: 'success', 
            text: `✅ ${data.amount_withdrawn} XLM withdrawn to your wallet!` 
          });
        } else {
          setMessage({ type: 'info', text: 'No balance to withdraw' });
        }
        fetchUserStatus();
        checkAccountBalance();
        return;
      }
      
      // If there's an XDR, we need to sign it (contract withdraw)
      if (data.xdr && data.needs_signing) {
        setMessage({ type: 'info', text: '🔗 Please sign the CONTRACT withdraw in Freighter...' });
        
        // Step 2: Sign with Freighter
        const signResult = await signTransaction(data.xdr, {
          networkPassphrase: NETWORK_PASSPHRASE,
        });
        
        if (signResult.error) {
          throw new Error(signResult.error);
        }
        
        // Step 3: Submit signed transaction
        const submitRes = await fetch('/api/submit-withdraw', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            signed_xdr: signResult.signedTxXdr,
            bot_id: botId,
            user_public_key: wallet.publicKey,
          }),
        });
        
        const submitData = await submitRes.json();
        
        if (submitData.success) {
          setMessage({ 
            type: 'success', 
            text: `🔗 ${submitData.amount_withdrawn} XLM withdrawn from contract to your wallet!` 
          });
        } else {
          throw new Error(submitData.error || 'Withdraw submission failed');
        }
      }
      
      fetchUserStatus();
      checkAccountBalance();
      
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Withdrawal failed';
      if (errorMessage.includes('User declined')) {
        setMessage({ type: 'warning', text: 'Transaction cancelled' });
      } else {
        setMessage({ type: 'error', text: errorMessage });
      }
    } finally {
      setActionLoading(null);
    }
  };

  const getActiveBotInfo = (botId: string): ActiveBot | undefined => {
    return userStatus?.active_bots.find((b: ActiveBot) => b.bot_id === botId);
  };

  if (loading) {
    return (
      <div className="container">
        <div className="loading">
          <div className="spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <header className="header">
        <h1>🐋 Profit Sharing Platform</h1>
        <p>Follow trading bots, simulate with $1000 virtual balance, pay commission only on profits!</p>
      </header>

      {message && (
        <div className={`alert alert-${message.type}`}>
          {message.text}
        </div>
      )}

      {/* Wallet Connection Section */}
      <div className="generate-account">
        <h3>🔗 Stellar Wallet Connection</h3>
        
        {freighterInstalled === false && (
          <div className="alert alert-warning" style={{ marginBottom: '1rem' }}>
            <strong>Freighter Wallet Required!</strong><br />
            <a 
              href="https://www.freighter.app/" 
              target="_blank" 
              rel="noopener noreferrer"
              style={{ color: '#0070f3', textDecoration: 'underline' }}
            >
              👉 Install Freighter Browser Extension
            </a>
            <br />
            <small>After installation, refresh the page and switch to TESTNET in Freighter settings.</small>
          </div>
        )}
        
        {!wallet.isConnected ? (
          <>
            <p>Connect your Stellar wallet to deposit commission and start trading simulation.</p>
            <div className="btn-group">
              <button 
                className="btn btn-primary" 
                onClick={connectWallet}
                disabled={!freighterInstalled || actionLoading === 'connect'}
              >
                {actionLoading === 'connect' ? 'Connecting...' : '🦊 Connect Freighter Wallet'}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="keypair-display">
              <div className="keypair-item">
                <div className="keypair-label">Connected Wallet</div>
                <div className="keypair-value">{wallet.publicKey}</div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.5rem' }}>
                <div className="keypair-item">
                  <div className="keypair-label">Network</div>
                  <div className="keypair-value" style={{ background: wallet.network === 'TESTNET' ? '#d1fae5' : '#fef3c7' }}>
                    {wallet.network === 'TESTNET' ? '✅ Testnet' : `⚠️ ${wallet.network}`}
                  </div>
                </div>
                <div className="keypair-item">
                  <div className="keypair-label">XLM Balance</div>
                  <div className="keypair-value">{xlmBalance || 'Loading...'} XLM</div>
                </div>
              </div>
            </div>
            <div className="btn-group">
              <button className="btn btn-primary" onClick={checkAccountBalance}>
                🔄 Refresh Balance
              </button>
              <button 
                className="btn" 
                style={{ background: '#e5e7eb', color: '#374151' }}
                onClick={disconnectWallet}
              >
                Disconnect
              </button>
            </div>
          </>
        )}

        <div style={{ marginTop: '1rem', padding: '0.75rem', background: '#f0f9ff', borderRadius: '8px', fontSize: '0.85rem' }}>
          <strong>💡 Need Testnet XLM?</strong><br />
          <a 
            href="https://laboratory.stellar.org/#account-creator?network=test" 
            target="_blank" 
            rel="noopener noreferrer" 
            style={{ color: '#0070f3' }}
          >
            Stellar Laboratory
          </a>
          {' '}→ Paste your public key → Click &quot;Get test network lumens&quot;
        </div>
      </div>

      {/* Info Box */}
      <div style={{ 
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
        color: 'white', 
        padding: '1.5rem', 
        borderRadius: '12px', 
        marginBottom: '2rem' 
      }}>
        <h3 style={{ margin: '0 0 0.5rem 0' }}>📊 How It Works</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
          <div style={{ background: 'rgba(255,255,255,0.1)', padding: '1rem', borderRadius: '8px' }}>
            <strong>1️⃣ Deposit Commission</strong><br />
            <small>Pay XLM to get bot access</small>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', padding: '1rem', borderRadius: '8px' }}>
            <strong>2️⃣ $1000 Simulation</strong><br />
            <small>Trade with virtual balance</small>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', padding: '1rem', borderRadius: '8px' }}>
            <strong>3️⃣ Daily Performance</strong><br />
            <small>Random returns -3% to +5%</small>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', padding: '1rem', borderRadius: '8px' }}>
            <strong>4️⃣ Commission Deduction</strong><br />
            <small>XLM deducted only on profits</small>
          </div>
        </div>
      </div>

      {/* Bot Grid */}
      <h2 style={{ marginBottom: '1rem' }}>🤖 Trading Bots</h2>
      
      {bots.length === 0 ? (
        <div className="alert alert-warning">
          No bots found. Make sure Python backend is running on port 5328.
        </div>
      ) : (
        <div className="bot-grid">
          {bots.map((bot) => {
            const activeBotInfo = getActiveBotInfo(bot.id);
            const isActive = !!activeBotInfo;
            const isAccessible = activeBotInfo?.is_accessible ?? false;
            const isExpanded = expandedBot === bot.id;
            
            return (
              <div key={bot.id} className="bot-card" style={{ 
                border: !isAccessible && isActive ? '2px solid #ef4444' : undefined 
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3>{bot.name}</h3>
                  <span className={`status-badge ${isActive ? (isAccessible ? 'active' : 'inactive') : 'inactive'}`}>
                    {isActive ? (isAccessible ? `Day ${activeBotInfo?.current_day || 0}` : '⚠️ No Commission') : 'Inactive'}
                  </span>
                </div>
                
                <p className="strategy">{bot.strategy}</p>
                
                <div className="details">
                  <div className="detail-item" style={{ background: '#fef3c7', padding: '0.5rem', borderRadius: '6px' }}>
                    <div className="detail-label">🧑‍💻 Developer Commission</div>
                    <div className="detail-value" style={{ color: '#b45309', fontWeight: 'bold' }}>{bot.developer_rate || 30}% of profits</div>
                  </div>
                  <div className="detail-item" style={{ background: '#dbeafe', padding: '0.5rem', borderRadius: '6px' }}>
                    <div className="detail-label">🏢 Platform Commission</div>
                    <div className="detail-value" style={{ color: '#1d4ed8', fontWeight: 'bold' }}>{bot.platform_rate || 10}% of profits</div>
                  </div>
                  <div className="detail-item">
                    <div className="detail-label">📊 Total Commission</div>
                    <div className="detail-value">{bot.total_commission || (bot.developer_rate + bot.platform_rate) || 40}% (from your deposit)</div>
                  </div>
                  <div className="detail-item">
                    <div className="detail-label">Min Commission Deposit</div>
                    <div className="detail-value">{bot.min_commission_deposit} XLM</div>
                  </div>
                  {isActive && activeBotInfo && (
                    <>
                      <div className="detail-item" style={{ 
                        background: activeBotInfo.commission_balance > 0 ? '#d1fae5' : '#fee2e2',
                        padding: '0.5rem',
                        borderRadius: '6px'
                      }}>
                        <div className="detail-label">💰 Commission Balance (XLM)</div>
                        <div className="detail-value" style={{ 
                          color: activeBotInfo.commission_balance > 0 ? '#059669' : '#dc2626', 
                          fontWeight: 'bold',
                          fontSize: '1.2rem'
                        }}>
                          {activeBotInfo.commission_balance.toFixed(4)} XLM
                        </div>
                      </div>
                      <div className="detail-item" style={{ background: '#ede9fe', padding: '0.5rem', borderRadius: '6px' }}>
                        <div className="detail-label">📊 Simulation Balance ($)</div>
                        <div className="detail-value" style={{ 
                          color: activeBotInfo.simulation_balance >= activeBotInfo.starting_balance ? '#7c3aed' : '#dc2626',
                          fontWeight: 'bold',
                          fontSize: '1.2rem'
                        }}>
                          ${activeBotInfo.simulation_balance.toFixed(2)}
                        </div>
                      </div>
                      <div className="detail-item">
                        <div className="detail-label">Total Profit/Loss ($)</div>
                        <div className="detail-value" style={{ color: activeBotInfo.total_profit >= 0 ? '#10b981' : '#ef4444' }}>
                          {activeBotInfo.total_profit >= 0 ? '+' : ''}${activeBotInfo.total_profit.toFixed(2)}
                        </div>
                      </div>
                      <div className="detail-item">
                        <div className="detail-label">Commission Paid (XLM)</div>
                        <div className="detail-value" style={{ color: '#f59e0b' }}>
                          {activeBotInfo.total_commission_paid.toFixed(4)} XLM
                        </div>
                      </div>
                    </>
                  )}
                </div>

                {/* Daily Simulation Controls */}
                {isActive && activeBotInfo && (
                  <div className="profit-section">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <h4 style={{ margin: 0 }}>📈 Daily Simulation</h4>
                      <button 
                        className="btn"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', background: '#e5e7eb' }}
                        onClick={() => setExpandedBot(isExpanded ? null : bot.id)}
                      >
                        {isExpanded ? '▲ Hide' : '▼ Table'}
                      </button>
                    </div>
                    
                    {/* Warning if commission depleted */}
                    {!isAccessible && (
                      <div style={{ 
                        background: '#fef2f2', 
                        border: '1px solid #fecaca', 
                        padding: '0.75rem', 
                        borderRadius: '8px', 
                        marginBottom: '0.5rem',
                        fontSize: '0.85rem'
                      }}>
                        ⚠️ <strong>Commission balance depleted!</strong><br />
                        Add more commission to continue.
                      </div>
                    )}
                    
                    <div className="btn-group" style={{ marginBottom: '0.5rem' }}>
                      <button 
                        className="btn btn-success"
                        onClick={() => handleSimulateDay(bot.id)}
                        disabled={!!actionLoading || !isAccessible}
                        style={{ flex: 2 }}
                      >
                        {actionLoading === `simulate-${bot.id}` ? '⏳ Processing...' : '▶️ Next Day'}
                      </button>
                      <button 
                        className="btn"
                        onClick={() => handleReset(bot.id)}
                        disabled={!!actionLoading}
                        style={{ background: '#6366f1', color: 'white' }}
                      >
                        {actionLoading === `reset-${bot.id}` ? '⏳' : '🔄 Reset'}
                      </button>
                    </div>

                    {/* Top-up Button */}
                    <button 
                      className="btn"
                      onClick={() => openTopupModal(bot)}
                      disabled={!!actionLoading}
                      style={{ 
                        width: '100%', 
                        background: '#10b981', 
                        color: 'white',
                        marginBottom: '0.5rem'
                      }}
                    >
                      ➕ Add Commission
                    </button>

                    {/* Daily History Table */}
                    {isExpanded && activeBotInfo.daily_history && (
                      <div style={{ 
                        maxHeight: '300px', 
                        overflowY: 'auto', 
                        border: '1px solid #e5e7eb', 
                        borderRadius: '8px',
                        marginTop: '0.5rem'
                      }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.7rem' }}>
                          <thead style={{ position: 'sticky', top: 0, background: '#f3f4f6' }}>
                            <tr>
                              <th style={{ padding: '0.4rem', textAlign: 'left', borderBottom: '2px solid #e5e7eb' }}>Day</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb' }}>%</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb' }}>Profit</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb', background: '#fef3c7' }}>🧑‍💻 Dev</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb', background: '#dbeafe' }}>🏢 Platform</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb' }}>Total</th>
                              <th style={{ padding: '0.4rem', textAlign: 'right', borderBottom: '2px solid #e5e7eb' }}>Balance</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activeBotInfo.daily_history.map((day) => (
                              <tr key={day.day} style={{ borderBottom: '1px solid #e5e7eb' }}>
                                <td style={{ padding: '0.3rem', fontWeight: 'bold' }}>
                                  {day.day === 0 ? '🏁' : day.day}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: day.performance_percent >= 0 ? '#10b981' : '#ef4444',
                                  fontWeight: 'bold'
                                }}>
                                  {day.day === 0 ? '-' : `${day.performance_percent >= 0 ? '+' : ''}${day.performance_percent}%`}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: day.profit_usd >= 0 ? '#10b981' : '#ef4444'
                                }}>
                                  {day.day === 0 ? '-' : `$${day.profit_usd.toFixed(0)}`}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: '#b45309',
                                  background: '#fffbeb'
                                }}>
                                  {day.day === 0 ? '-' : (day.developer_xlm?.toFixed(4) || '0')}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: '#1d4ed8',
                                  background: '#eff6ff'
                                }}>
                                  {day.day === 0 ? '-' : (day.platform_xlm?.toFixed(4) || '0')}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: '#f59e0b',
                                  fontWeight: 'bold'
                                }}>
                                  {day.day === 0 ? '-' : day.commission_xlm.toFixed(4)}
                                </td>
                                <td style={{ 
                                  padding: '0.3rem', 
                                  textAlign: 'right',
                                  color: day.commission_balance > 0 ? '#059669' : '#dc2626',
                                  fontWeight: 'bold'
                                }}>
                                  {day.commission_balance.toFixed(2)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot style={{ background: '#f9fafb', fontWeight: 'bold', fontSize: '0.75rem' }}>
                            <tr>
                              <td colSpan={2} style={{ padding: '0.4rem', textAlign: 'left' }}>TOPLAM</td>
                              <td style={{ 
                                padding: '0.4rem', 
                                textAlign: 'right',
                                color: activeBotInfo.total_profit >= 0 ? '#10b981' : '#ef4444'
                              }}>
                                ${activeBotInfo.total_profit.toFixed(0)}
                              </td>
                              <td style={{ padding: '0.4rem', textAlign: 'right', color: '#b45309', background: '#fffbeb' }}>
                                {activeBotInfo.daily_history.reduce((sum, d) => sum + (d.developer_xlm || 0), 0).toFixed(4)}
                              </td>
                              <td style={{ padding: '0.4rem', textAlign: 'right', color: '#1d4ed8', background: '#eff6ff' }}>
                                {activeBotInfo.daily_history.reduce((sum, d) => sum + (d.platform_xlm || 0), 0).toFixed(4)}
                              </td>
                              <td style={{ padding: '0.4rem', textAlign: 'right', color: '#f59e0b' }}>
                                {activeBotInfo.total_commission_paid.toFixed(4)}
                              </td>
                              <td style={{ padding: '0.4rem', textAlign: 'right', color: '#059669' }}>
                                {activeBotInfo.commission_balance.toFixed(2)}
                              </td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {/* Action Buttons */}
                <div className="btn-group" style={{ marginTop: '1rem' }}>
                  {!isActive ? (
                    <button 
                      className="btn btn-primary"
                      onClick={() => openDepositModal(bot)}
                      disabled={!wallet.isConnected || actionLoading !== null}
                    >
                      {wallet.isConnected ? '💰 Deposit & Start' : 'Connect Wallet'}
                    </button>
                  ) : (
                    <button 
                      className="btn btn-danger"
                      onClick={() => handleWithdraw(bot.id)}
                      disabled={actionLoading !== null}
                    >
                      {actionLoading === `withdraw-${bot.id}` ? 'Processing...' : '💸 Withdraw & Exit'}
                    </button>
                  )}
                </div>

                {/* Vault Address */}
                <div className="address" style={{ marginTop: '0.5rem' }}>
                  <strong>Vault:</strong>{' '}
                  <a 
                    href={`https://stellar.expert/explorer/testnet/account/${bot.deposit_address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#0070f3', fontSize: '0.8rem' }}
                  >
                    {bot.deposit_address ? `${bot.deposit_address.substring(0, 8)}...${bot.deposit_address.slice(-8)}` : 'Loading...'}
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Initial Deposit Modal */}
      {showDepositModal && selectedBot && (
        <div className="modal-overlay" onClick={() => setShowDepositModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>💰 Deposit & Start</h2>
            <p style={{ marginBottom: '1rem', color: '#6b7280' }}>
              Deposit commission balance for <strong>{selectedBot.name}</strong>.
            </p>
            
            <div style={{ background: '#f0fdf4', padding: '1rem', borderRadius: '8px', marginBottom: '1rem' }}>
              <strong>🎮 What Happens?</strong>
              <ul style={{ margin: '0.5rem 0 0 1rem', padding: 0, fontSize: '0.9rem' }}>
                <li>Simulation starts with $1000 virtual balance</li>
                <li>Daily random returns between -3% and +5%</li>
                <li>Commission deducted only on profitable days</li>
                <li>Bot access closes when commission balance is depleted</li>
              </ul>
            </div>
            
            <div className="form-group">
              <label className="form-label">Commission Amount (XLM)</label>
              <input
                type="number"
                className="form-input"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                min={selectedBot.min_commission_deposit}
              />
              <small style={{ color: '#6b7280' }}>Minimum: {selectedBot.min_commission_deposit} XLM</small>
            </div>
            
            <div className="alert alert-info">
              <strong>Transaction Details:</strong><br />
              From: {wallet.publicKey?.substring(0, 12)}...{wallet.publicKey?.slice(-8)}<br />
              To: {selectedBot.deposit_address?.substring(0, 12)}...{selectedBot.deposit_address?.slice(-8)}<br />
              Amount: {depositAmount} XLM<br />
              Commission Rate: {selectedBot.commission_rate}% (profits only)
            </div>

            <div className="modal-actions">
              <button 
                className="btn btn-primary"
                onClick={handleDeposit}
                disabled={actionLoading === 'deposit'}
              >
                {actionLoading === 'deposit' ? '✍️ Sign in Freighter...' : '✅ Sign & Start'}
              </button>
              <button 
                className="btn" 
                style={{ background: '#e5e7eb', color: '#374151' }}
                onClick={() => setShowDepositModal(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Top-up Modal */}
      {showTopupModal && selectedBot && (
        <div className="modal-overlay" onClick={() => setShowTopupModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>➕ Add Commission</h2>
            <p style={{ marginBottom: '1rem', color: '#6b7280' }}>
              Add more commission balance for <strong>{selectedBot.name}</strong>.
            </p>
            
            <div style={{ background: '#fef3c7', padding: '1rem', borderRadius: '8px', marginBottom: '1rem' }}>
              <strong>💡 Info:</strong>
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>
                When you add more commission, your simulation continues from where it left off.
                If your balance runs out, bot access closes but you can reset to start fresh.
              </p>
            </div>
            
            <div className="form-group">
              <label className="form-label">Additional Commission Amount (XLM)</label>
              <input
                type="number"
                className="form-input"
                value={topupAmount}
                onChange={(e) => setTopupAmount(e.target.value)}
                min="1"
              />
            </div>
            
            <div className="alert alert-info">
              <strong>Transaction Details:</strong><br />
              Amount: +{topupAmount} XLM commission balance
            </div>

            <div className="modal-actions">
              <button 
                className="btn btn-primary"
                onClick={handleTopup}
                disabled={actionLoading === 'topup'}
              >
                {actionLoading === 'topup' ? '✍️ Sign in Freighter...' : '✅ Sign & Add'}
              </button>
              <button 
                className="btn" 
                style={{ background: '#e5e7eb', color: '#374151' }}
                onClick={() => setShowTopupModal(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
