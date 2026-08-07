#ifndef GEARED_STEPPER_H
#define GEARED_STEPPER_H

#include <Arduino.h>
#include <AccelStepper.h>

class GearedStepper {
public:
    GearedStepper(uint8_t step_pin, uint8_t dir_pin, uint8_t enable_pin,
                  uint8_t ms1_pin,  uint8_t ms2_pin,  uint8_t ms3_pin,
                  long    base_steps_per_rot,
                  float   gear_ratio = 1.0f);

    void begin();
    void setMaxSpeed(float speed);
    void setAcceleration(float acceleration);
    void moveTo(long absolute);
    void move(long relative);
    bool run();
    void runToPosition();
    void stop();

    long  currentPosition();
    void  setCurrentPosition(long position);
    long  distanceToGo();
    long  targetPosition();
    bool  isRunning();

    void enable();
    void disable();

    void setMicrostepResolution(int resolution);   // 1, 2, 4, 8, 16
    int  getMicrostepResolution() const;

    float getGearRatio()              const;
    long  getBaseStepsPerRotation()   const;       // motor side
    long  getOutputStepsPerRotation() const;       // turntable side
    float maxSpeed();
    float acceleration();

private:
    const uint8_t _enable_pin;
    const uint8_t _ms1_pin, _ms2_pin, _ms3_pin;

    const long  _base_steps_per_rot;
    const float _gear_ratio;
    int         _microstep_resolution;

    AccelStepper _stepper;
};

#endif /* GEARED_STEPPER_H */
