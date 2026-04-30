# Lesson 18 - Rock Paper Scissors Vision V2

This lesson mirrors Lesson 8 using the V2 robot object.

Use this lesson to practise:
- detecting a player's hand gesture
- mapping camera labels to rock / paper / scissors
- using `myRobot.camera`, `myRobot.eyes`, and `myRobot.voice` as game signals
- deciding how the robot should respond

## Main namespaces
- `myRobot.vision`
- `myRobot.camera`
- `myRobot.voice`
- `myRobot.eyes`
- `myRobot.buzzer`

## Suggested rock-paper-scissors mapping
- `fist` = rock
- `open_palm` = paper
- `peace` = scissors

## Suggested game signals
- blue lights = ready
- yellow lights = draw or retry
- green lights = robot win
- red lights = player win
- camera shake = countdown motion
- speech = tell the player what is happening
