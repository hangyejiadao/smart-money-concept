//+------------------------------------------------------------------+
//|                                       SmartMoneyConceptsEA.mq5   |
//|  Derivative of LuxAlgo Smart Money Concepts (Pine v5)            |
//|  MQL5 indicator port: Ismael Ladjohounlou / GeneralTradingSarl   |
//|  Original work (c) LuxAlgo, CC BY-NC-SA 4.0                      |
//|  https://creativecommons.org/licenses/by-nc-sa/4.0/              |
//|  Non-commercial use only, attribution required, share alike.     |
//+------------------------------------------------------------------+
#property copyright "LuxAlgo / GeneralTradingSarl / hangyejiadao"
#property link      "https://github.com/hangyejiadao/Smart-Money-Concepts"
#property version   "1.00"
#property strict
#property description "SMC EA: H4 swing bias + chart-timeframe internal BOS/CHoCH, order block/FVG tap, 2R."
#property description "Algorithm aligned with LuxAlgo Smart Money Concepts. CC BY-NC-SA 4.0, non-commercial."

#include <Trade\Trade.mqh>
#include <SmartMoneyConceptsEA\SMCEngine.mqh>

input group "Safety"
input bool             InpAllowLive          = false;           // Allow live trading (keep false for tester)

input group "Structure"
input int              InpSwingLength        = 50;              // Swing length
input bool             InpConfluenceFilter   = false;           // Internal confluence filter
input bool             InpUseBos             = true;            // Trade internal BOS
input bool             InpUseChoch           = true;            // Trade internal CHoCH
input bool             InpUseInternalOB      = true;            // Use internal order blocks
input bool             InpUseSwingOB         = true;            // Use swing order blocks
input bool             InpUseFvg             = true;            // Use fair value gaps
input bool             InpFvgThreshold       = true;            // FVG auto threshold
input bool             InpRequireZone        = true;            // Require OB/FVG tap
input int              InpZoneLookback       = 8;               // Zone lookback bars
input int              InpMaxBars            = 6000;            // Warmup closed bars

input group "Bias"
input ENUM_TIMEFRAMES  InpBiasTF             = PERIOD_H4;       // Higher-timeframe swing bias
input bool             InpUseHtfBias         = true;            // Require HTF swing trend

input group "Risk"
input ulong            InpMagic              = 20261119;        // Magic number
input double           InpRiskPercent        = 0.5;             // Risk percent of equity
input double           InpRewardMultiple     = 2.0;             // Take-profit R multiple
input double           InpSlAtrBuffer        = 0.20;            // SL ATR(200) buffer
input int              InpMinSlPoints        = 80;              // Min stop distance (points)
input int              InpMaxSlPoints        = 2500;            // Max stop distance (points)
input double           InpMaxLongLocation    = 0.62;            // Max long premium/discount location
input double           InpMinShortLocation   = 0.38;            // Min short premium/discount location
input int              InpCooldownBars       = 4;               // Cooldown after an order
input int              InpMaxSpreadPoints    = 40;              // Max spread (points)
input int              InpSlippagePoints     = 30;              // Deviation (points)
input double           InpMinLot             = 0.0;             // Min lot (0 = symbol min)
input double           InpMaxLot             = 0.0;             // Max lot (0 = symbol max)

input group "Session"
input bool             InpSessionFilter      = false;           // Session filter
input double           InpSessionStartHour   = 9.0;             // Session start hour
input double           InpSessionEndHour     = 22.0;            // Session end hour
input bool             InpFlatFriday         = false;           // Flatten Friday
input double           InpFridayCutoffHour   = 21.0;            // Friday cutoff hour
input bool             InpVerbose            = true;            // Verbose journal

CTrade      g_trade;
CSMCEngine  g_ltf;
CSMCEngine  g_htf;
bool        g_sameTf      = true;
datetime    g_lastBarTime = 0;
int         g_cooldownUntil = -1;
int         g_barIndex    = 0;
int         g_longZoneBar = -1000;
int         g_shortZoneBar= -1000;
SmcZone     g_longZone;
SmcZone     g_shortZone;

int CountEnginePositions()
  {
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      count++;
     }
   return count;
  }

void CloseEnginePositions(const string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      if(!g_trade.PositionClose(ticket))
         Print("SMC close failed ", ticket, " ", g_trade.ResultRetcode(), " ", reason);
      else
         if(InpVerbose)
            Print("SMC closed ", ticket, " ", reason);
     }
  }

bool InSession(const datetime t)
  {
   if(!InpSessionFilter)
      return true;
   MqlDateTime dt;
   TimeToStruct(t, dt);
   double hour = dt.hour + dt.min / 60.0;
   bool inside = (InpSessionStartHour <= InpSessionEndHour)
                 ? (hour >= InpSessionStartHour && hour < InpSessionEndHour)
                 : (hour >= InpSessionStartHour || hour < InpSessionEndHour);
   if(!inside)
      return false;
   if(InpFlatFriday && dt.day_of_week == 5 && hour >= InpFridayCutoffHour)
      return false;
   return true;
  }

bool ShouldFlattenFriday(const datetime t)
  {
   if(!InpFlatFriday)
      return false;
   MqlDateTime dt;
   TimeToStruct(t, dt);
   double hour = dt.hour + dt.min / 60.0;
   return (dt.day_of_week == 5 && hour >= InpFridayCutoffHour);
  }

double NormalizeLot(double lot)
  {
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(InpMinLot > 0)
      minLot = MathMax(minLot, InpMinLot);
   if(InpMaxLot > 0)
      maxLot = MathMin(maxLot, InpMaxLot);
   if(step <= 0)
      step = 0.01;
   lot = MathFloor(lot / step + 1e-12) * step;
   lot = MathMax(minLot, MathMin(maxLot, lot));
   int digits = 0;
   double tmp = step;
   while(tmp < 1.0 && digits < 8)
     {
      tmp *= 10.0;
      digits++;
     }
   return NormalizeDouble(lot, digits);
  }

double LotsForRisk(const double slDistance)
  {
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0 || tickSize <= 0 || slDistance <= 0)
      return 0;
   double risk = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double lossPerLot = slDistance / tickSize * tickValue;
   if(lossPerLot <= 0)
      return 0;
   return NormalizeLot(risk / lossPerLot);
  }

double NormalizePrice(const double price)
  {
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
  }

bool CopyClosedRates(const ENUM_TIMEFRAMES tf, const int maxBars, MqlRates &rates[])
  {
   int available = Bars(_Symbol, tf);
   if(available < 3)
      return false;
   int need = MathMin(maxBars, available - 1);
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(_Symbol, tf, 1, need, rates);
   return copied > 0;
  }

void WarmEngines()
  {
   MqlRates ltf[];
   if(CopyClosedRates(_Period, InpMaxBars, ltf))
      g_ltf.FeedClosedRates(ltf, ArraySize(ltf));
   if(!g_sameTf)
     {
      MqlRates htf[];
      if(CopyClosedRates(InpBiasTF, InpMaxBars, htf))
         g_htf.FeedClosedRates(htf, ArraySize(htf));
     }
  }

void UpdateEngines()
  {
   MqlRates ltf[];
   ArraySetAsSeries(ltf, false);
   if(CopyRates(_Symbol, _Period, 1, 1, ltf) == 1)
      g_ltf.FeedClosedBar(ltf[0].time, ltf[0].open, ltf[0].high, ltf[0].low, ltf[0].close);
   if(!g_sameTf)
     {
      MqlRates htf[];
      ArraySetAsSeries(htf, false);
      if(CopyRates(_Symbol, InpBiasTF, 1, 1, htf) == 1)
         g_htf.FeedClosedBar(htf[0].time, htf[0].open, htf[0].high, htf[0].low, htf[0].close);
     }
  }

int HtfTrend(const SmcSnapshot &ltfSnap)
  {
   if(!InpUseHtfBias || g_sameTf)
      return ltfSnap.swingTrend;
   SmcSnapshot htfSnap = g_htf.Snapshot();
   return htfSnap.swingTrend;
  }

bool InternalBreak(const SmcSnapshot &snap, const int side, string &kind)
  {
   kind = "";
   if(side == SMC_BULLISH)
     {
      if(InpUseBos && snap.internalBullBos)
        { kind = "BOS"; return true; }
      if(InpUseChoch && snap.internalBullChoch)
        { kind = "CHoCH"; return true; }
     }
   else
     {
      if(InpUseBos && snap.internalBearBos)
        { kind = "BOS"; return true; }
      if(InpUseChoch && snap.internalBearChoch)
        { kind = "CHoCH"; return true; }
     }
   return false;
  }

bool TryEnter()
  {
   if(CountEnginePositions() > 0)
      return false;
   if(g_barIndex < g_cooldownUntil)
      return false;

   SmcSnapshot snap = g_ltf.Snapshot();
   if(snap.time == 0 || snap.atr == SMC_NA || snap.atr <= 0)
      return false;
   if(!InSession(snap.time))
      return false;

   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spread > InpMaxSpreadPoints)
      return false;

   SmcZone longZone, shortZone;
   bool tappedLong  = g_ltf.TappedZone(SMC_BULLISH, snap.high, snap.low, snap.close, longZone);
   bool tappedShort = g_ltf.TappedZone(SMC_BEARISH, snap.high, snap.low, snap.close, shortZone);
   if(tappedLong)
     {
      g_longZone    = longZone;
      g_longZoneBar = g_barIndex;
     }
   if(tappedShort)
     {
      g_shortZone    = shortZone;
      g_shortZoneBar = g_barIndex;
     }
   if(g_barIndex - g_longZoneBar > InpZoneLookback)
      g_longZone.found = false;
   if(g_barIndex - g_shortZoneBar > InpZoneLookback)
      g_shortZone.found = false;

   string bullKind = "", bearKind = "";
   bool bullBreak = InternalBreak(snap, SMC_BULLISH, bullKind);
   bool bearBreak = InternalBreak(snap, SMC_BEARISH, bearKind);
   if(bullBreak && bearBreak)
      return false;
   if(!bullBreak && !bearBreak)
      return false;

   int side = bullBreak ? SMC_BULLISH : SMC_BEARISH;
   int htfTrend = HtfTrend(snap);
   if(side == SMC_BULLISH && (snap.swingTrend != SMC_BULLISH || htfTrend != SMC_BULLISH))
      return false;
   if(side == SMC_BEARISH && (snap.swingTrend != SMC_BEARISH || htfTrend != SMC_BEARISH))
      return false;

   if(snap.trailingTop == SMC_NA || snap.trailingBottom == SMC_NA || snap.trailingTop <= snap.trailingBottom)
      return false;
   double span = snap.trailingTop - snap.trailingBottom;
   if(span < MathMax(8.0 * snap.atr, 50.0 * _Point))
      return false;
   double location = (snap.close - snap.trailingBottom) / span;
   if(side == SMC_BULLISH && location > InpMaxLongLocation)
      return false;
   if(side == SMC_BEARISH && location < InpMinShortLocation)
      return false;

   SmcZone zone;
   zone.found = false;
   if(side == SMC_BULLISH && g_longZone.found)
      zone = g_longZone;
   if(side == SMC_BEARISH && g_shortZone.found)
      zone = g_shortZone;
   if(!zone.found)
     {
      if(InpRequireZone)
         return false;
      zone.found = true;
      zone.name  = "structure";
      zone.low   = (side == SMC_BULLISH ? snap.low : snap.close);
      zone.high  = (side == SMC_BULLISH ? snap.close : snap.high);
     }

   double buffer = MathMax(InpSlAtrBuffer * snap.atr, 2.0 * _Point);
   double sl     = (side == SMC_BULLISH ? MathMin(zone.low, snap.low) - buffer : MathMax(zone.high, snap.high) + buffer);
   double entry  = (side == SMC_BULLISH ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID));
   if(entry <= 0)
      return false;
   double slDistance = MathAbs(entry - sl);
   double slPoints   = slDistance / _Point;
   if(slPoints < InpMinSlPoints || slPoints > InpMaxSlPoints)
      return false;

   double tp = (side == SMC_BULLISH ? entry + InpRewardMultiple * slDistance : entry - InpRewardMultiple * slDistance);
   double lot = LotsForRisk(slDistance);
   if(lot <= 0)
      return false;

   sl = NormalizePrice(sl);
   tp = NormalizePrice(tp);
   string comment = "SMC " + (side == SMC_BULLISH ? "buy " : "sell ") + (bullBreak ? bullKind : bearKind);
   bool ok = false;
   if(side == SMC_BULLISH)
      ok = g_trade.Buy(lot, _Symbol, 0, sl, tp, comment);
   else
      ok = g_trade.Sell(lot, _Symbol, 0, sl, tp, comment);

   g_cooldownUntil = g_barIndex + InpCooldownBars;
   if(!ok)
     {
      Print("SMC order failed ", g_trade.ResultRetcode(), " ", g_trade.ResultRetcodeDescription());
      return false;
     }
   if(InpVerbose)
      Print(comment, " lot=", lot, " sl=", sl, " tp=", tp, " zone=", zone.name, " loc=", DoubleToString(location, 3));
   return true;
  }

int OnInit()
  {
   bool tester = (bool)MQLInfoInteger(MQL_TESTER);
   if(!tester && !InpAllowLive)
     {
      Print("SmartMoneyConceptsEA refuses live trading. Enable InpAllowLive only after a backtest review.");
      return INIT_FAILED;
     }

   g_sameTf = (!InpUseHtfBias || InpBiasTF == PERIOD_CURRENT || InpBiasTF == _Period);
   g_ltf.Configure(InpSwingLength, InpConfluenceFilter, InpFvgThreshold, InpUseSwingOB, InpUseInternalOB);
   if(!g_sameTf)
      g_htf.Configure(InpSwingLength, InpConfluenceFilter, InpFvgThreshold, InpUseSwingOB, InpUseInternalOB);

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetAsyncMode(false);
   long fill = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((fill & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      if((fill & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
         g_trade.SetTypeFilling(ORDER_FILLING_FOK);
      else
         g_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   g_longZone.found = false;
   g_shortZone.found = false;
   WarmEngines();
   g_lastBarTime = iTime(_Symbol, _Period, 0);
   g_barIndex = g_ltf.Count();
   if(InpVerbose)
      Print("SMC EA ready bars=", g_ltf.Count(), " sameTf=", g_sameTf, " biasTF=", EnumToString(InpBiasTF));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
  }

void OnTick()
  {
   datetime nowBar = iTime(_Symbol, _Period, 0);
   if(ShouldFlattenFriday(TimeCurrent()) && CountEnginePositions() > 0)
      CloseEnginePositions("Friday cutoff");

   if(nowBar == g_lastBarTime)
      return;
   g_lastBarTime = nowBar;
   UpdateEngines();
   g_barIndex = g_ltf.Count();
   TryEnter();
  }
//+------------------------------------------------------------------+
