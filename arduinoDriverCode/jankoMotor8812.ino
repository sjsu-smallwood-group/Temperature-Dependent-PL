/*
  8801 Picomotor Controller — Single Driver, 3 Corners (A/B/C)
  Integration-ready: NO ENABLE REQUIRED (always ready to move).

  ============================
  WIRING SUMMARY (EXACT MAP)
  ============================
    DB-15 pin  8  (StepA) -> Arduino D3   (STEP A)
    DB-15 pin 15  (DirA)  -> Arduino D4   (DIR  A)

    DB-15 pin  7  (StepB) -> Arduino D5   (STEP B)
    DB-15 pin 14  (DirB)  -> Arduino D7   (DIR  B)

    DB-15 pin  9  (StepC) -> Arduino D6   (STEP C)
    DB-15 pin 13  (DirC)  -> Arduino D8   (DIR  C)

    DB-15 pin 11  (GND)   -> Arduino GND  (common ground, REQUIRED)
    DB-15 pin 12  (Clock) -> Arduino D10  (OPTIONAL: input only)

  Notes:
  - STEP uses NEGATIVE EDGE stepping: idle HIGH; a HIGH->LOW transition = one step.
  - Do NOT connect 8801 +5V (DB-15 pin 5) to Arduino 5V. Power Arduino separately; share GND only.
  - Clock (DB-15 pin 12) is optional; if used, configure D10 as INPUT and never drive it.
*/

#include <Arduino.h>

// ---------- Put CornerPins FIRST to avoid Arduino auto-prototype issues ----------
struct CornerPins { uint8_t dir; uint8_t step; };

// ---------- Forward prototypes (prevents IDE from auto-making wrong ones) ----------
void idleHigh(const CornerPins& p);
void setDir(const CornerPins& p, long steps);
void pulseStep(const CornerPins& p);
bool checkSafety();
void moveCorner(const CornerPins& p, char name, long steps, long& pos);
void printHelp();
void handleCommand(String line);

// ---------------- Pin Map (matches your wiring exactly) ----------------
#define STEP_A 3
#define DIR_A  4

#define STEP_B 5
#define DIR_B  7

#define STEP_C 6
#define DIR_C  8

#define CLK_8801 10   // optional read-only clock from 8801; set to -1 to disable

// ---------------- Aux / Safety (customize or disable as needed) --------
#define EMERGENCY_STOP_PIN 12   // LOW = pressed (uses INPUT_PULLUP)
#define CURRENT_SENSE_PIN  A0   // optional current sense (0..1023), or tie to GND if unused
#define LED_PIN            A3   // status LED (on = ok/idle)
#define TRIGGER_OUT_PIN    A2   // reserved output (idle LOW)

// ---------------- Motion parameters -----------------------------------
struct MotionParams {
  unsigned int pulse_low_us = 200; // LOW hold time for step pulse (µs); falling edge does the step
  unsigned int gap_ms       = 6;   // delay between steps (ms) => sets speed
  uint8_t      takeup       = 6;   // pre-steps to overcome stiction/backlash
  unsigned int settle_ms    = 40;  // settle after move (ms)
} mp;

// ---------------- Safety thresholds (optional) -------------------------
const int   MAX_CURRENT_MA      = 500;                  // optional
const float CURRENT_MA_PER_CNT  = 1000.0f / 1023.0f;    // scale ADC→mA (example)

// ---------------- State -------------------------------------------------
struct SystemState {
  long posA = 0, posB = 0, posC = 0;
  bool moving = false;
  bool e_stop = false;
  bool overcurrent = false;
  unsigned long last_heartbeat_ms = 0;
} st;

inline void heartbeat(){ st.last_heartbeat_ms = millis(); }

// ---------------- Corner pin bundles -----------------------------------
const CornerPins CORNER_A = { DIR_A, STEP_A };
const CornerPins CORNER_B = { DIR_B, STEP_B };
const CornerPins CORNER_C = { DIR_C, STEP_C };

// ---------------- Helpers ----------------------------------------------
void idleHigh(const CornerPins& p){
  // Negative-edge stepping: idle HIGH on STEP; DIR default LOW
  if (p.dir)  digitalWrite(p.dir, LOW);
  if (p.step) digitalWrite(p.step, HIGH);
}

void setDir(const CornerPins& p, long steps){
  // HIGH = forward, LOW = reverse (flip if your mechanics are inverted)
  digitalWrite(p.dir, (steps > 0) ? HIGH : LOW);
  delayMicroseconds(1500); // small settle after DIR change
}

void pulseStep(const CornerPins& p){
  // generate falling edge while idling HIGH
  digitalWrite(p.step, HIGH);
  delayMicroseconds(2);
  digitalWrite(p.step, LOW);                  // FALLING EDGE = one step
  delayMicroseconds(mp.pulse_low_us);        // hold LOW
  digitalWrite(p.step, HIGH);                // back to idle HIGH
}

bool checkSafety(){
  // E-STOP: active LOW
  pinMode(EMERGENCY_STOP_PIN, INPUT_PULLUP);
  st.e_stop = (digitalRead(EMERGENCY_STOP_PIN) == LOW);

  // Optional current sense (ignore if not wired)
  int adc = analogRead(CURRENT_SENSE_PIN);
  int mA  = (int)(adc * CURRENT_MA_PER_CNT + 0.5f);
  st.overcurrent = (mA > MAX_CURRENT_MA);

  if (st.e_stop) {
    Serial.println(F("ERROR: E-STOP"));
    return false;
  }
  if (st.overcurrent) {
    Serial.print(F("ERROR: Overcurrent mA=")); Serial.println(mA);
    return false;
  }
  return true;
}

void moveCorner(const CornerPins& p, char name, long steps, long& pos){
  if (steps == 0) return;
  if (!checkSafety()) return;

  long target = pos + steps;
  st.moving = true;
  setDir(p, steps);

  // Take-up steps to overcome stiction/backlash
  for (uint8_t i=0; i<mp.takeup; ++i) {
    if (!checkSafety()) { st.moving = false; return; }
    pulseStep(p); heartbeat(); delay(mp.gap_ms);
  }
  // Main motion
  for (long i=0, n=labs(steps); i<n; ++i) {
    if (!checkSafety()) { st.moving = false; return; }
    pulseStep(p); heartbeat(); delay(mp.gap_ms);
  }

  delay(mp.settle_ms);
  pos = target;
  st.moving = false;
}

// ---------------- UI / Commands ----------------------------------------
void printHelp(){
  Serial.println(F("=== 8801 Picomotor Controller (A/B/C) ==="));
  Serial.println(F("Commands:"));
  Serial.println(F("  MOVE A <steps> | MOVE B <steps> | MOVE C <steps>   (steps can be +/-)"));
  Serial.println(F("  ZERO     (reset positions to 0)"));
  Serial.println(F("  POSITION (report positions)"));
  Serial.println(F("  STATUS   (basic status)"));
  Serial.println(F("  SAFETY   (report e-stop/overcurrent)"));
  Serial.println(F("  SET_TIMING <pulse_us> <gap_ms> <takeup> <settle_ms>"));
  Serial.println(F("  PING     (responds PONG)"));
  Serial.println(F("  HELP"));
  Serial.println(F("Notes: negative-edge stepping; share GND; do NOT tie 8801 +5V to Arduino 5V."));
}

void handleCommand(String line){
  line.trim(); if (!line.length()) return;
  int sp1 = line.indexOf(' ');
  String cmd = (sp1==-1)? line : line.substring(0, sp1);
  cmd.toUpperCase();

  if (cmd == F("PING")) { Serial.println(F("PONG")); heartbeat(); return; }
  if (cmd == F("HELP")) { printHelp(); return; }

  if (cmd == F("ZERO")){
    st.posA = st.posB = st.posC = 0;
    Serial.println(F("OK"));
    heartbeat();
    return;
  }

  if (cmd == F("POSITION")){
    Serial.print(F("POS A=")); Serial.print(st.posA);
    Serial.print(F(" B="));    Serial.print(st.posB);
    Serial.print(F(" C="));    Serial.println(st.posC);
    return;
  }

  if (cmd == F("STATUS")){
    Serial.print(F("STATUS MOVING=")); Serial.print(st.moving?1:0);
    Serial.print(F(" A=")); Serial.print(st.posA);
    Serial.print(F(" B=")); Serial.print(st.posB);
    Serial.print(F(" C=")); Serial.println(st.posC);
    return;
  }

  if (cmd == F("SAFETY")){
    checkSafety();
    Serial.print(F("SAFETY E="));  Serial.print(st.e_stop?1:0);
    Serial.print(F(" OC="));       Serial.println(st.overcurrent?1:0);
    return;
  }

  if (cmd == F("SET_TIMING")){
    long v[4]={0,0,0,0}; int cnt=0, start=sp1+1;
    for (int i=start;i<=line.length() && cnt<4;i++){
      if (i==line.length() || line[i]==' '){
        String tok = line.substring(start,i); tok.trim();
        if (tok.length()) v[cnt++] = tok.toInt();
        start = i+1;
      }
    }
    if (cnt==4){
      mp.pulse_low_us = (unsigned int)max(50L, v[0]);  // keep >= ~50 µs for reliability
      mp.gap_ms       = (unsigned int)max(0L,  v[1]);
      mp.takeup       = (uint8_t)max(0L,       v[2]);
      mp.settle_ms    = (unsigned int)max(0L,  v[3]);
      Serial.println(F("OK"));
      heartbeat();
    } else {
      Serial.println(F("ERROR: SET_TIMING needs 4 ints"));
    }
    return;
  }

  if (cmd == F("MOVE")){
    int sp2 = line.indexOf(' ', sp1+1); if (sp2==-1){ Serial.println(F("ERROR: MOVE syntax")); return; }
    String which = line.substring(sp1+1, sp2); which.trim(); which.toUpperCase();
    long steps = line.substring(sp2+1).toInt();

    if (which == F("A")) { moveCorner(CORNER_A, 'A', steps, st.posA); if(!st.moving) Serial.println(F("OK")); return; }
    if (which == F("B")) { moveCorner(CORNER_B, 'B', steps, st.posB); if(!st.moving) Serial.println(F("OK")); return; }
    if (which == F("C")) { moveCorner(CORNER_C, 'C', steps, st.posC); if(!st.moving) Serial.println(F("OK")); return; }

    Serial.println(F("ERROR: MOVE expects A, B, or C"));
    return;
  }

  if (cmd == F("STOP")){
    st.moving = false;
    digitalWrite(TRIGGER_OUT_PIN, LOW);
    Serial.println(F("OK"));
    return;
  }

  Serial.println(F("ERROR: Unknown command"));
}

// ---------------- Setup / Loop -----------------------------------------
void setup(){
  // Configure outputs
  pinMode(DIR_A, OUTPUT);  pinMode(STEP_A, OUTPUT);
  pinMode(DIR_B, OUTPUT);  pinMode(STEP_B, OUTPUT);
  pinMode(DIR_C, OUTPUT);  pinMode(STEP_C, OUTPUT);

  // Idle states (negative-edge stepping): DIR LOW, STEP HIGH
  idleHigh(CORNER_A);
  idleHigh(CORNER_B);
  idleHigh(CORNER_C);

  pinMode(EMERGENCY_STOP_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);          digitalWrite(LED_PIN, LOW);
  pinMode(TRIGGER_OUT_PIN, OUTPUT);  digitalWrite(TRIGGER_OUT_PIN, LOW);
  if (CLK_8801 >= 0) pinMode(CLK_8801, INPUT); // optional

  Serial.begin(9600);
  while(!Serial){;}
  st.last_heartbeat_ms = millis();

  Serial.println(F("READY"));
  Serial.println(F("8801 Picomotor Controller v1.1 (no ENABLE required)"));
  Serial.println(F("Type HELP for commands"));
}

void loop(){
  // Status LED on when not e-stop and not moving
  digitalWrite(LED_PIN, (!st.e_stop && !st.moving) ? HIGH : LOW);

  if (Serial.available() > 0){
    String line = Serial.readStringUntil('\n');
    if (line.length()) handleCommand(line);
  }

  checkSafety();
  delay(1);
}