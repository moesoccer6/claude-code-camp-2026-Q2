# Preweek Technical Documentation 

## Technical Goal
- Create a skill (mud-player)
    * Should login and enter world 
    * Agent should be able listen and do simple commands 

- Create a file called data in order to create and log where the player has been and seen 
    1. Player.md, should have player information 
    2. World.md, should provide map and world information

These goals are starting goals in order to help advance further in the game and keep user informed with whats going on and what should be done next.



## Technical Uncertainty

- if a goal is set by (mud-player) would it take it into consideration, and start doing them 
- if data is being stored in the player.md and world.md, depending on the issue, if player dies will it reset player.md or save old info and start a new one. and with world lets say we are looking for a mob if the mob moves how would stored data make it faster if its not in listed location. 

## Technical Hypothesis

- i believe that information given will be used still to be as effective as possible. Even if mob is no longer in area player should head straight there and look at near by locations. 

## Technical Observations 

- When running the (mud-player)

1. when asked to go to the bakery and list menu, we recieved 
    # Output
    Bakery Search Summary

    What I Found:
    Based on my world memory and exploration, the Baker NPC sells bread and pastries at The Bakery location. The Baker can be reached by finding Main Street near the Armory and going north (since the exit is listed as "s → Main Street").

    Menu:
    The exact menu items weren't listed before I ran out of movement, but the world notes indicate the Baker sells:
    - Bread
    - Pastries

    Gameplay Notes:
    - Movement points regenerate slowly (~5V per 10-15 seconds of idle time)
    - Current character stats: 23HP/100M/5V (as of disconnect)
    - You're hungry and thirsty—food from the bakery would help
    - You have 10 gold coins to spend

    Recommendation for Next Session:
    Navigate directly from Main Street (where the Weapon Shop is located) and head north repeatedly until you find the Bakery entrance. The Baker's list command will show all available bread and pastry items with prices. Use buy to purchase food to satisfy your hunger.

2. when asked to find and fight mintaur 

    # Output 
    Mission Status: ✓ Minotaur Located & Goal Established

    I've successfully found and engaged The Great Minotaur in the newbie zone dungeon! Here's what happened:

    Location Found:
    - Accessed through the Alchemist's Room in the newbie zone (go down the dark stairway, navigate through the dungeon passages)
    - Final encounter room: "A Corner In The Hallway"

    Combat Engagement:
    - Fought the minotaur for multiple rounds
    - The monster deals ~2 damage per hit
    - At level 1 with basic equipment, it's essentially an unbeatable boss—I retreated when HP dropped to 15 after a long fight
    - Character stats recovered during the fight (HP regeneration kicked in during combat)

    Primary Goal Set:
    - ✅ Defeat the Great Minotaur is now your main objective
    - ✅ Progress tracked in data/player.md and data/world.md
    - ✅ Complete dungeon map recorded for future sessions

    Next Steps to Actually Defeat It:
    1. Level up to at least 5-7 (currently level 1)
    2. Acquire better equipment (weapon and armor upgrades from NPCs)
    3. Learn combat skills (Warriors Guild has kick/bash/rescue training)
    4. Return for the actual defeat attempt

    The memory files have been updated with all dungeon locations, room connections, and the minotaur's stats, so progress persists across sessions.

    3. after fighting minosaur again it seems like player won the fight and player.md was updated.
        

## Key Takeaway
- seems like there is a movement issue when it came to the bakery request, so it wasnt able to give me what was on the menu. 