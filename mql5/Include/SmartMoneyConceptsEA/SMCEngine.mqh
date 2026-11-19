#ifndef SMC_ENGINE_MQH
#define SMC_ENGINE_MQH

#define SMC_BULLISH_LEG  1
#define SMC_BEARISH_LEG  0
#define SMC_BULLISH      1
#define SMC_BEARISH     -1
#define SMC_NA           EMPTY_VALUE
#define SMC_NA_INT       INT_MIN
#define SMC_PINE_EPS     1e-10

struct SmcPivot
  {
   double            currentLevel;
   double            lastLevel;
   bool              crossed;
   long              barTime;
   int               barIndex;
  };

struct SmcOrderBlock
  {
   double            barHigh;
   double            barLow;
   long              barTime;
   int               barIndex;
   int               bias;
  };

struct SmcFairValueGap
  {
   double            top;
   double            bottom;
   int               bias;
   int               barIndex;
  };

struct SmcTrailing
  {
   double            top;
   double            bottom;
   long              barTime;
   int               barIndex;
   long              lastTopTime;
   long              lastBottomTime;
  };

struct SmcZone
  {
   string            name;
   double            low;
   double            high;
   bool              found;
  };

struct SmcSnapshot
  {
   datetime          time;
   double            open;
   double            high;
   double            low;
   double            close;
   double            atr;
   int               swingTrend;
   int               internalTrend;
   double            trailingTop;
   double            trailingBottom;
   bool              internalBullBos;
   bool              internalBullChoch;
   bool              internalBearBos;
   bool              internalBearChoch;
   bool              swingBullBos;
   bool              swingBullChoch;
   bool              swingBearBos;
   bool              swingBearChoch;
  };

class CSMCEngine
  {
private:
   datetime          m_t[];
   double            m_o[];
   double            m_h[];
   double            m_l[];
   double            m_c[];
   double            m_ph[];
   double            m_pl[];
   int               m_count;
   int               m_start;

   SmcPivot          m_swingHigh;
   SmcPivot          m_swingLow;
   SmcPivot          m_internalHigh;
   SmcPivot          m_internalLow;
   int               m_swingTrend;
   int               m_internalTrend;
   SmcTrailing       m_trailing;
   SmcOrderBlock     m_swingOBs[];
   SmcOrderBlock     m_internalOBs[];
   SmcFairValueGap   m_fvgs[];

   double            m_atrMeasure;
   double            m_atrSum;
   int               m_atrCount;
   double            m_cumTrueRange;
   double            m_cumFvgDelta;
   int               m_legValue[3];
   int               m_legPrevious[3];
   double            m_crossLevel[4];
   bool              m_bullishBar[2];
   bool              m_bearishBar[2];

   int               m_swingSize;
   bool              m_confluenceFilter;
   bool              m_fvgThreshold;
   bool              m_useSwingOB;
   bool              m_useInternalOB;

   bool              m_intBullBos;
   bool              m_intBullChoch;
   bool              m_intBearBos;
   bool              m_intBearChoch;
   bool              m_swBullBos;
   bool              m_swBullChoch;
   bool              m_swBearBos;
   bool              m_swBearChoch;

   bool              Gt(const double a, const double b) const { return a - b > SMC_PINE_EPS; }
   bool              Lt(const double a, const double b) const { return b - a > SMC_PINE_EPS; }
   bool              Ge(const double a, const double b) const { return !Lt(a, b); }
   bool              Le(const double a, const double b) const { return !Gt(a, b); }
   bool              Eq(const double a, const double b) const { return !Gt(a, b) && !Lt(a, b); }

   void              InitPivot(SmcPivot &p);
   void              StoreBar(const datetime t, const double o, const double h, const double l, const double c);
   void              OnBar(const int i);
   void              UpdateAtr(const double trueRange);
   int               Leg(const int i, const int size, const int site);
   void              GetCurrentStructure(const int i, const int size, const bool internal);
   void              NewPivotLow(SmcPivot &p, const int i, const int size, const bool internal);
   void              NewPivotHigh(SmcPivot &p, const int i, const int size, const bool internal);
   void              DisplayStructure(const int i, const bool internal);
   void              BullishBreak(SmcPivot &p, int &trend, const int i, const bool internal, const bool extraCondition);
   void              BearishBreak(SmcPivot &p, int &trend, const int i, const bool internal, const bool extraCondition);
   void              StoreOrderBlock(const SmcPivot &p, const bool internal, const int bias, const int i);
   void              DeleteOrderBlocks(SmcOrderBlock &blocks[], const int i);
   void              DeleteFairValueGaps(const int i);
   void              DetectFairValueGaps(const int i);
   void              UpdateTrailing(const int i);
   void              UnshiftOB(SmcOrderBlock &a[], const SmcOrderBlock &v);
   void              UnshiftFvg(const SmcFairValueGap &v);
   void              RemoveOB(SmcOrderBlock &a[], const int index);
   void              RemoveFvg(const int index);

public:
                     CSMCEngine(void);
   void              Configure(const int swingSize, const bool confluenceFilter, const bool fvgThreshold, const bool useSwingOB, const bool useInternalOB);
   void              Reset(void);
   bool              FeedClosedBar(const datetime t, const double o, const double h, const double l, const double c);
   bool              FeedClosedRates(const MqlRates &rates[], const int n);
   int               Count(void) const { return m_count; }
   datetime          LastTime(void) const { return m_count > 0 ? m_t[m_count - 1] : 0; }
   SmcSnapshot       Snapshot(void) const;
   bool              TappedZone(const int bias, const double barHigh, const double barLow, const double barClose, SmcZone &zone) const;
  };

void CSMCEngine::CSMCEngine(void)
  {
   m_swingSize         = 50;
   m_confluenceFilter  = false;
   m_fvgThreshold      = true;
   m_useSwingOB        = true;
   m_useInternalOB     = true;
   Reset();
  }

void CSMCEngine::Configure(const int swingSize, const bool confluenceFilter, const bool fvgThreshold, const bool useSwingOB, const bool useInternalOB)
  {
   m_swingSize        = MathMax(10, swingSize);
   m_confluenceFilter = confluenceFilter;
   m_fvgThreshold     = fvgThreshold;
   m_useSwingOB       = useSwingOB;
   m_useInternalOB    = useInternalOB;
  }

void CSMCEngine::InitPivot(SmcPivot &p)
  {
   p.currentLevel = SMC_NA;
   p.lastLevel    = SMC_NA;
   p.crossed      = false;
   p.barTime      = (m_count > 0 ? (long)m_t[m_start] : 0);
   p.barIndex     = m_start;
  }

void CSMCEngine::Reset(void)
  {
   ArrayResize(m_t, 0, 1024);
   ArrayResize(m_o, 0, 1024);
   ArrayResize(m_h, 0, 1024);
   ArrayResize(m_l, 0, 1024);
   ArrayResize(m_c, 0, 1024);
   ArrayResize(m_ph, 0, 1024);
   ArrayResize(m_pl, 0, 1024);
   m_count = 0;
   m_start = 0;
   InitPivot(m_swingHigh);
   InitPivot(m_swingLow);
   InitPivot(m_internalHigh);
   InitPivot(m_internalLow);
   m_swingTrend    = 0;
   m_internalTrend = 0;
   ArrayResize(m_fvgs, 0, 64);
   ArrayResize(m_swingOBs, 0, 128);
   ArrayResize(m_internalOBs, 0, 128);
   m_trailing.top            = SMC_NA;
   m_trailing.bottom         = SMC_NA;
   m_trailing.barTime        = 0;
   m_trailing.barIndex       = SMC_NA_INT;
   m_trailing.lastTopTime    = 0;
   m_trailing.lastBottomTime = 0;
   m_atrMeasure   = SMC_NA;
   m_atrSum       = 0;
   m_atrCount     = 0;
   m_cumTrueRange = 0;
   m_cumFvgDelta  = 0;
   for(int k = 0; k < 3; k++)
     {
      m_legValue[k]    = 0;
      m_legPrevious[k] = SMC_NA_INT;
     }
   for(int k = 0; k < 4; k++)
      m_crossLevel[k] = SMC_NA;
   for(int k = 0; k < 2; k++)
     {
      m_bullishBar[k] = true;
      m_bearishBar[k] = true;
     }
   m_intBullBos = m_intBullChoch = m_intBearBos = m_intBearChoch = false;
   m_swBullBos  = m_swBullChoch  = m_swBearBos  = m_swBearChoch  = false;
  }

void CSMCEngine::UnshiftOB(SmcOrderBlock &a[], const SmcOrderBlock &v)
  {
   int n = ArraySize(a);
   ArrayResize(a, n + 1, 128);
   for(int k = n; k > 0; k--)
      a[k] = a[k - 1];
   a[0] = v;
  }

void CSMCEngine::UnshiftFvg(const SmcFairValueGap &v)
  {
   int n = ArraySize(m_fvgs);
   ArrayResize(m_fvgs, n + 1, 64);
   for(int k = n; k > 0; k--)
      m_fvgs[k] = m_fvgs[k - 1];
   m_fvgs[0] = v;
  }

void CSMCEngine::RemoveOB(SmcOrderBlock &a[], const int index)
  {
   int n = ArraySize(a);
   for(int k = index; k < n - 1; k++)
      a[k] = a[k + 1];
   ArrayResize(a, n - 1, 128);
  }

void CSMCEngine::RemoveFvg(const int index)
  {
   int n = ArraySize(m_fvgs);
   for(int k = index; k < n - 1; k++)
      m_fvgs[k] = m_fvgs[k + 1];
   ArrayResize(m_fvgs, n - 1, 64);
  }

void CSMCEngine::StoreBar(const datetime t, const double o, const double h, const double l, const double c)
  {
   int n = m_count;
   ArrayResize(m_t, n + 1, 1024);
   ArrayResize(m_o, n + 1, 1024);
   ArrayResize(m_h, n + 1, 1024);
   ArrayResize(m_l, n + 1, 1024);
   ArrayResize(m_c, n + 1, 1024);
   ArrayResize(m_ph, n + 1, 1024);
   ArrayResize(m_pl, n + 1, 1024);
   m_t[n] = t;
   m_o[n] = o;
   m_h[n] = h;
   m_l[n] = l;
   m_c[n] = c;
   m_ph[n] = h;
   m_pl[n] = l;
   m_count = n + 1;
  }

bool CSMCEngine::FeedClosedBar(const datetime t, const double o, const double h, const double l, const double c)
  {
   if(t <= 0)
      return false;
   if(m_count > 0 && t <= m_t[m_count - 1])
      return false;
   StoreBar(t, o, h, l, c);
   OnBar(m_count - 1);
   return true;
  }

bool CSMCEngine::FeedClosedRates(const MqlRates &rates[], const int n)
  {
   if(n <= 0)
      return false;
   if(m_count > 0 && rates[0].time != m_t[0])
      Reset();
   bool added = false;
   datetime last = (m_count > 0 ? m_t[m_count - 1] : 0);
   for(int i = 0; i < n; i++)
     {
      if(rates[i].time <= last)
         continue;
      StoreBar(rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close);
      OnBar(m_count - 1);
      last = rates[i].time;
      added = true;
     }
   return added;
  }

void CSMCEngine::UpdateAtr(const double trueRange)
  {
   m_atrCount++;
   if(m_atrCount < 200)
     {
      m_atrSum    += trueRange;
      m_atrMeasure = SMC_NA;
     }
   else
      if(m_atrCount == 200)
        {
         m_atrSum    += trueRange;
         m_atrMeasure = m_atrSum / 200.0;
        }
      else
        {
         double alpha = 1.0 / 200.0;
         m_atrMeasure = alpha * trueRange + (1.0 - alpha) * m_atrMeasure;
        }
  }

int CSMCEngine::Leg(const int i, const int size, const int site)
  {
   bool newLegHigh = false;
   bool newLegLow  = false;
   int  j          = i - size;
   if(j >= m_start)
     {
      double highest = m_h[i];
      double lowest  = m_l[i];
      for(int k = i - size + 1; k < i; k++)
        {
         if(m_h[k] > highest)
            highest = m_h[k];
         if(m_l[k] < lowest)
            lowest = m_l[k];
        }
      newLegHigh = Gt(m_h[j], highest);
      newLegLow  = Lt(m_l[j], lowest);
     }
   if(newLegHigh)
      m_legValue[site] = SMC_BEARISH_LEG;
   else
      if(newLegLow)
         m_legValue[site] = SMC_BULLISH_LEG;
   return m_legValue[site];
  }

void CSMCEngine::NewPivotLow(SmcPivot &p, const int i, const int size, const bool internal)
  {
   double lowSize = m_l[i - size];
   p.lastLevel    = p.currentLevel;
   p.currentLevel = lowSize;
   p.crossed      = false;
   p.barTime      = (long)m_t[i - size];
   p.barIndex     = i - size;
   if(!internal)
     {
      m_trailing.bottom         = p.currentLevel;
      m_trailing.barTime        = p.barTime;
      m_trailing.barIndex       = p.barIndex;
      m_trailing.lastBottomTime = p.barTime;
     }
  }

void CSMCEngine::NewPivotHigh(SmcPivot &p, const int i, const int size, const bool internal)
  {
   double highSize = m_h[i - size];
   p.lastLevel    = p.currentLevel;
   p.currentLevel = highSize;
   p.crossed      = false;
   p.barTime      = (long)m_t[i - size];
   p.barIndex     = i - size;
   if(!internal)
     {
      m_trailing.top         = p.currentLevel;
      m_trailing.barTime     = p.barTime;
      m_trailing.barIndex    = p.barIndex;
      m_trailing.lastTopTime = p.barTime;
     }
  }

void CSMCEngine::GetCurrentStructure(const int i, const int size, const bool internal)
  {
   int site       = internal ? 1 : 0;
   int currentLeg = Leg(i, size, site);
   int previous   = m_legPrevious[site];
   m_legPrevious[site] = currentLeg;
   if(previous == SMC_NA_INT)
      return;
   bool newPivot = (currentLeg - previous != 0);
   bool pivotLow = (currentLeg - previous == +1);
   if(newPivot)
     {
      if(pivotLow)
        {
         if(internal)
            NewPivotLow(m_internalLow, i, size, true);
         else
            NewPivotLow(m_swingLow, i, size, false);
        }
      else
        {
         if(internal)
            NewPivotHigh(m_internalHigh, i, size, true);
         else
            NewPivotHigh(m_swingHigh, i, size, false);
        }
     }
  }

void CSMCEngine::StoreOrderBlock(const SmcPivot &p, const bool internal, const int bias, const int i)
  {
   if((internal && !m_useInternalOB) || (!internal && !m_useSwingOB))
      return;
   int from = p.barIndex;
   if(from < m_start || from >= i)
      return;
   int parsedIndex = from;
   if(bias == SMC_BEARISH)
     {
      double extreme = m_ph[from];
      for(int k = from + 1; k < i; k++)
         extreme = MathMax(extreme, m_ph[k]);
      while(parsedIndex < i - 1 && !Eq(m_ph[parsedIndex], extreme))
         parsedIndex++;
     }
   else
     {
      double extreme = m_pl[from];
      for(int k = from + 1; k < i; k++)
         extreme = MathMin(extreme, m_pl[k]);
      while(parsedIndex < i - 1 && !Eq(m_pl[parsedIndex], extreme))
         parsedIndex++;
     }
   SmcOrderBlock block;
   block.barHigh  = m_ph[parsedIndex];
   block.barLow   = m_pl[parsedIndex];
   block.barTime  = (long)m_t[parsedIndex];
   block.barIndex = parsedIndex;
   block.bias     = bias;
   if(internal)
     {
      if(ArraySize(m_internalOBs) >= 100)
         ArrayResize(m_internalOBs, ArraySize(m_internalOBs) - 1, 128);
      UnshiftOB(m_internalOBs, block);
     }
   else
     {
      if(ArraySize(m_swingOBs) >= 100)
         ArrayResize(m_swingOBs, ArraySize(m_swingOBs) - 1, 128);
      UnshiftOB(m_swingOBs, block);
     }
  }

void CSMCEngine::BullishBreak(SmcPivot &p, int &trend, const int i, const bool internal, const bool extraCondition)
  {
   int    site     = internal ? 0 : 2;
   double level    = p.currentLevel;
   double previous = m_crossLevel[site];
   m_crossLevel[site] = level;
   bool crossover = i > m_start && level != SMC_NA && previous != SMC_NA && Gt(m_c[i], level) && Le(m_c[i - 1], previous);
   if(crossover && !p.crossed && extraCondition)
     {
      bool choch = (trend == SMC_BEARISH);
      if(internal)
        {
         m_intBullChoch = choch;
         m_intBullBos   = !choch;
        }
      else
        {
         m_swBullChoch = choch;
         m_swBullBos   = !choch;
        }
      p.crossed = true;
      trend     = SMC_BULLISH;
      StoreOrderBlock(p, internal, SMC_BULLISH, i);
     }
  }

void CSMCEngine::BearishBreak(SmcPivot &p, int &trend, const int i, const bool internal, const bool extraCondition)
  {
   int    site     = internal ? 1 : 3;
   double level    = p.currentLevel;
   double previous = m_crossLevel[site];
   m_crossLevel[site] = level;
   bool crossunder = i > m_start && level != SMC_NA && previous != SMC_NA && Lt(m_c[i], level) && Ge(m_c[i - 1], previous);
   if(crossunder && !p.crossed && extraCondition)
     {
      bool choch = (trend == SMC_BULLISH);
      if(internal)
        {
         m_intBearChoch = choch;
         m_intBearBos   = !choch;
        }
      else
        {
         m_swBearChoch = choch;
         m_swBearBos   = !choch;
        }
      p.crossed = true;
      trend     = SMC_BEARISH;
      StoreOrderBlock(p, internal, SMC_BEARISH, i);
     }
  }

void CSMCEngine::DisplayStructure(const int i, const bool internal)
  {
   int site = internal ? 0 : 1;
   if(m_confluenceFilter)
     {
      m_bullishBar[site] = Gt(m_h[i] - MathMax(m_c[i], m_o[i]), MathMin(m_c[i], m_o[i] - m_l[i]));
      m_bearishBar[site] = Lt(m_h[i] - MathMax(m_c[i], m_o[i]), MathMin(m_c[i], m_o[i] - m_l[i]));
     }
   bool extraBull = internal ? (m_internalHigh.currentLevel != SMC_NA && m_swingHigh.currentLevel != SMC_NA && !Eq(m_internalHigh.currentLevel, m_swingHigh.currentLevel) && m_bullishBar[site]) : true;
   bool extraBear = internal ? (m_internalLow.currentLevel != SMC_NA && m_swingLow.currentLevel != SMC_NA && !Eq(m_internalLow.currentLevel, m_swingLow.currentLevel) && m_bearishBar[site]) : true;
   if(internal)
     {
      BullishBreak(m_internalHigh, m_internalTrend, i, true, extraBull);
      BearishBreak(m_internalLow, m_internalTrend, i, true, extraBear);
     }
   else
     {
      BullishBreak(m_swingHigh, m_swingTrend, i, false, extraBull);
      BearishBreak(m_swingLow, m_swingTrend, i, false, extraBear);
     }
  }

void CSMCEngine::DeleteOrderBlocks(SmcOrderBlock &blocks[], const int i)
  {
   double bearSrc = m_h[i];
   double bullSrc = m_l[i];
   for(int index = 0; index < ArraySize(blocks); index++)
     {
      bool crossed = false;
      if(Gt(bearSrc, blocks[index].barHigh) && blocks[index].bias == SMC_BEARISH)
         crossed = true;
      else
         if(Lt(bullSrc, blocks[index].barLow) && blocks[index].bias == SMC_BULLISH)
            crossed = true;
      if(crossed)
         RemoveOB(blocks, index);
     }
  }

void CSMCEngine::DeleteFairValueGaps(const int i)
  {
   for(int index = 0; index < ArraySize(m_fvgs); index++)
     {
      if((Lt(m_l[i], m_fvgs[index].bottom) && m_fvgs[index].bias == SMC_BULLISH) ||
         (Gt(m_h[i], m_fvgs[index].top) && m_fvgs[index].bias == SMC_BEARISH))
         RemoveFvg(index);
     }
  }

void CSMCEngine::DetectFairValueGaps(const int i)
  {
   double lastClose = (i - 1 >= m_start ? m_c[i - 1] : SMC_NA);
   double lastOpen  = (i - 1 >= m_start ? m_o[i - 1] : SMC_NA);
   double last2High = (i - 2 >= m_start ? m_h[i - 2] : SMC_NA);
   double last2Low  = (i - 2 >= m_start ? m_l[i - 2] : SMC_NA);
   double currentHigh = m_h[i];
   double currentLow  = m_l[i];
   double barDeltaPercent = (lastClose == SMC_NA || lastOpen == SMC_NA || lastOpen == 0.0) ? SMC_NA : (lastClose - lastOpen) / (lastOpen * 100.0);
   double threshold = 0.0;
   if(m_fvgThreshold)
     {
      if(barDeltaPercent != SMC_NA)
         m_cumFvgDelta += MathAbs(barDeltaPercent);
      threshold = (i > m_start ? m_cumFvgDelta / (i - m_start) * 2.0 : SMC_NA);
     }
   bool valid = barDeltaPercent != SMC_NA && threshold != SMC_NA && currentHigh != SMC_NA && currentLow != SMC_NA && last2High != SMC_NA && last2Low != SMC_NA;
   bool bullish = valid && Gt(currentLow, last2High) && Gt(lastClose, last2High) && Gt(barDeltaPercent, threshold);
   bool bearish = valid && Lt(currentHigh, last2Low) && Lt(lastClose, last2Low) && Gt(-barDeltaPercent, threshold);
   if(bullish)
     {
      SmcFairValueGap fvg;
      fvg.top      = currentLow;
      fvg.bottom   = last2High;
      fvg.bias     = SMC_BULLISH;
      fvg.barIndex = i;
      UnshiftFvg(fvg);
     }
   if(bearish)
     {
      SmcFairValueGap fvg;
      fvg.top      = currentHigh;
      fvg.bottom   = last2Low;
      fvg.bias     = SMC_BEARISH;
      fvg.barIndex = i;
      UnshiftFvg(fvg);
     }
  }

void CSMCEngine::UpdateTrailing(const int i)
  {
   m_trailing.top            = (m_trailing.top == SMC_NA ? SMC_NA : MathMax(m_h[i], m_trailing.top));
   m_trailing.lastTopTime    = (m_trailing.top != SMC_NA && Eq(m_trailing.top, m_h[i])) ? (long)m_t[i] : m_trailing.lastTopTime;
   m_trailing.bottom         = (m_trailing.bottom == SMC_NA ? SMC_NA : MathMin(m_l[i], m_trailing.bottom));
   m_trailing.lastBottomTime = (m_trailing.bottom != SMC_NA && Eq(m_trailing.bottom, m_l[i])) ? (long)m_t[i] : m_trailing.lastBottomTime;
  }

void CSMCEngine::OnBar(const int i)
  {
   m_intBullBos = m_intBullChoch = m_intBearBos = m_intBearChoch = false;
   m_swBullBos  = m_swBullChoch  = m_swBearBos  = m_swBearChoch  = false;

   if(i == m_start)
     {
      InitPivot(m_swingHigh);
      InitPivot(m_swingLow);
      InitPivot(m_internalHigh);
      InitPivot(m_internalLow);
     }

   double trueRange = (i > m_start ? MathMax(MathMax(m_h[i] - m_l[i], MathAbs(m_h[i] - m_c[i - 1])), MathAbs(m_l[i] - m_c[i - 1])) : m_h[i] - m_l[i]);
   UpdateAtr(trueRange);
   bool highVol = (m_atrMeasure != SMC_NA && Ge(m_h[i] - m_l[i], 2.0 * m_atrMeasure));
   m_ph[i] = highVol ? m_l[i] : m_h[i];
   m_pl[i] = highVol ? m_h[i] : m_l[i];

   UpdateTrailing(i);
   DeleteFairValueGaps(i);
   GetCurrentStructure(i, m_swingSize, false);
   GetCurrentStructure(i, 5, true);
   DisplayStructure(i, true);
   DisplayStructure(i, false);
   if(m_useInternalOB)
      DeleteOrderBlocks(m_internalOBs, i);
   if(m_useSwingOB)
      DeleteOrderBlocks(m_swingOBs, i);
   DetectFairValueGaps(i);
  }

SmcSnapshot CSMCEngine::Snapshot(void) const
  {
   SmcSnapshot s;
   ZeroMemory(s);
   if(m_count <= 0)
      return s;
   int i = m_count - 1;
   s.time               = m_t[i];
   s.open               = m_o[i];
   s.high               = m_h[i];
   s.low                = m_l[i];
   s.close              = m_c[i];
   s.atr                = m_atrMeasure;
   s.swingTrend         = m_swingTrend;
   s.internalTrend      = m_internalTrend;
   s.trailingTop        = m_trailing.top;
   s.trailingBottom     = m_trailing.bottom;
   s.internalBullBos    = m_intBullBos;
   s.internalBullChoch  = m_intBullChoch;
   s.internalBearBos    = m_intBearBos;
   s.internalBearChoch  = m_intBearChoch;
   s.swingBullBos       = m_swBullBos;
   s.swingBullChoch     = m_swBullChoch;
   s.swingBearBos       = m_swBearBos;
   s.swingBearChoch     = m_swBearChoch;
   return s;
  }

bool CSMCEngine::TappedZone(const int bias, const double barHigh, const double barLow, const double barClose, SmcZone &zone) const
  {
   zone.found = false;
   zone.name  = "";
   zone.low   = 0;
   zone.high  = 0;
   double zLow  = 0;
   double zHigh = 0;
   bool   any   = false;
   string kinds = "";

   int nInt = ArraySize(m_internalOBs);
   for(int i = 0; i < nInt; i++)
     {
      if(m_internalOBs[i].bias != bias)
         continue;
      bool hit = false;
      if(bias == SMC_BULLISH && barLow <= m_internalOBs[i].barHigh && barClose >= m_internalOBs[i].barLow)
         hit = true;
      if(bias == SMC_BEARISH && barHigh >= m_internalOBs[i].barLow && barClose <= m_internalOBs[i].barHigh)
         hit = true;
      if(hit)
        {
         if(!any) { zLow = m_internalOBs[i].barLow; zHigh = m_internalOBs[i].barHigh; }
         else { zLow = MathMin(zLow, m_internalOBs[i].barLow); zHigh = MathMax(zHigh, m_internalOBs[i].barHigh); }
         any = true;
         if(StringFind(kinds, "ob") < 0)
            kinds += (kinds == "" ? "ob" : "+ob");
        }
     }

   int nSw = ArraySize(m_swingOBs);
   for(int i = 0; i < nSw; i++)
     {
      if(m_swingOBs[i].bias != bias)
         continue;
      bool hit = false;
      if(bias == SMC_BULLISH && barLow <= m_swingOBs[i].barHigh && barClose >= m_swingOBs[i].barLow)
         hit = true;
      if(bias == SMC_BEARISH && barHigh >= m_swingOBs[i].barLow && barClose <= m_swingOBs[i].barHigh)
         hit = true;
      if(hit)
        {
         if(!any) { zLow = m_swingOBs[i].barLow; zHigh = m_swingOBs[i].barHigh; }
         else { zLow = MathMin(zLow, m_swingOBs[i].barLow); zHigh = MathMax(zHigh, m_swingOBs[i].barHigh); }
         any = true;
         if(StringFind(kinds, "ob") < 0)
            kinds += (kinds == "" ? "ob" : "+ob");
        }
     }

   int nFvg = ArraySize(m_fvgs);
   for(int i = 0; i < nFvg; i++)
     {
      if(m_fvgs[i].bias != bias)
         continue;
      bool hit = false;
      if(bias == SMC_BULLISH && barLow <= m_fvgs[i].top && barClose >= m_fvgs[i].bottom)
         hit = true;
      if(bias == SMC_BEARISH && barHigh >= m_fvgs[i].bottom && barClose <= m_fvgs[i].top)
         hit = true;
      if(hit)
        {
         if(!any) { zLow = m_fvgs[i].bottom; zHigh = m_fvgs[i].top; }
         else { zLow = MathMin(zLow, m_fvgs[i].bottom); zHigh = MathMax(zHigh, m_fvgs[i].top); }
         any = true;
         if(StringFind(kinds, "fvg") < 0)
            kinds += (kinds == "" ? "fvg" : "+fvg");
        }
     }

   if(!any)
      return false;
   zone.found = true;
   zone.name  = kinds;
   zone.low   = zLow;
   zone.high  = zHigh;
   return true;
  }

#endif
