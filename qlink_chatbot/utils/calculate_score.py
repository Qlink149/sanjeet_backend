from qlink_chatbot.database.db_utils import get_attendee_activity_data
day1_correct={
  "screen_0_Select_Correct_Option_0": "3_Option_(D)",
  "screen_1_Select_Correct_Option_0": "0_Option_(A)",
  "screen_2_Select_Correct_Option_0": "2_Option_(C)",
  "screen_3_Select_Correct_Option_0": "1_Option_(B)"
}

day2_correct={
  "screen_0_Select_Correct_Option_0": "0_Option_(A)",
  "screen_1_Select_Correct_Option_0": "0_Option_(A)",
  "screen_2_Select_Correct_Option_0": "3_Option_(D)",
  "screen_3_Select_Correct_Option_0": "2_Option_(C)"
}

day3_correct={
  "screen_0_Select_Correct_Option_0": "0_Option_(A)",
  "screen_1_Select_Correct_Option_0": "0_Option_(A)",
  "screen_2_Select_Correct_Option_0": "3_Option_(D)",
  "screen_3_Select_Correct_Option_0": "2_Option_(C)"
}

def calculate_quiz_score(day: str, quiz_response: dict) -> int:
    """
    Calculate quiz score based on the day and user responses.
    
    Args:
        day: Day identifier ("day1", "day2", "day3")
        quiz_response: Dictionary containing user responses
        
    Returns:
        int: Score out of 4 questions
    """
    # Map day to correct answers
    correct_answers_map = {
        "day1": day1_correct,
        "day2": day2_correct,
        "day3": day3_correct
    }
    
    # Get correct answers for the specified day
    correct_answers = correct_answers_map.get(day.lower())
    if not correct_answers:
        raise ValueError(f"Invalid day: {day}. Must be day1, day2, or day3")
    
    score = 0
    
    # Check each question
    for question_key, correct_answer in correct_answers.items():
        user_answer = quiz_response.get(question_key, "")
        if user_answer == correct_answer:
            score += 1
    
    return score

def calculate_day_total_score(phone_number: str, day: str, quiz_response: dict) -> dict:
    """
    Calculate total score for a specific day.

    Scoring Rules:
    - Booth Visit: 25 points per booth
    - Session Attendance: 50 points per session
    - Quiz: 5 points per correct answer
    """

    # -------------------------
    # 1️⃣ Get Attendee Activity Data
    # -------------------------
    activity = get_attendee_activity_data(phone_number)

    if not activity.get("success"):
        return {"success": False, "error": "invalid_user"}

    visited_sessions = activity["data"].get("visited_sessions", [])
    visited_stalls = activity["data"].get("visited_stalls", [])

    # -------------------------
    # 2️⃣ Calculate Quiz Score (correct answers count)
    # -------------------------
    correct_answers_count = calculate_quiz_score(day, quiz_response)

    # Multiply by 5 (as required)
    quiz_points = correct_answers_count * 5

    # -------------------------
    # 3️⃣ Filter Sessions by Day
    # -------------------------
    day_sessions = [
        session for session in visited_sessions
        if session.get("day", "").lower() == day.lower()
    ]

    session_points = len(day_sessions) * 50

    # -------------------------
    # 4️⃣ Filter Stalls by Day
    # -------------------------
    day_stalls = [
        stall for stall in visited_stalls
        if stall.get("day", "").lower() == day.lower()
    ]

    booth_points = len(day_stalls) * 25

    # -------------------------
    # 🔥 Final Total
    # -------------------------
    total_score = quiz_points + session_points + booth_points

    return total_score