# -*- coding: utf-8 -*-
"""Scheduliability With Visualization.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1T-QBw2GQIuT3LGvB6hm5K77HlxkEPAVj
"""

!pip install z3-solver pandas openpyxl

import pandas as pd
from datetime import datetime, time
from z3 import *

# Upload these files manually in Colab before running:
# - realizations_IT_2023-2024.xlsx
# - reservations_Agora_2023-2024.xlsx

# Load and clean realization data
df = pd.read_excel("/content/realizations_IT_2023-2024.xlsx")
df.columns = df.columns.str.strip()
df["Starts"] = pd.to_datetime(df["Starts"], dayfirst=True, errors="coerce")
df["Ends"] = pd.to_datetime(df["Ends"], dayfirst=True, errors="coerce")
df = df.drop_duplicates(subset=["Code"]).reset_index(drop=True)

# Load and clean reservation file
res_df = pd.read_excel("/content/reservations_Agora_2023-2024.xlsx")
res_df.columns = res_df.columns.str.strip()

# Define your time slots
TIME_SLOTS = [(time(8, 0), time(9, 45)), (time(10, 0), time(11, 45)),
              (time(12, 0), time(13, 45)), (time(14, 0), time(15, 45))]

def get_time_slot_index(start_time):
    for i, (slot_start, slot_end) in enumerate(TIME_SLOTS):
        if slot_start <= start_time <= slot_end:
            return i
    return None

# Extract teacher preferences: (course_code, teacher) → [(day, slot), ...]
preferences = {}
for _, row in res_df.iterrows():
    course_ver = str(row.get("Course version", "")).strip()
    teacher = str(row.get("Booked for", "")).strip()
    start_str = str(row.get("Starts", "")).strip()

    if "-" not in course_ver or not teacher or not start_str:
        continue
    code = course_ver.split("-")[0].strip()

    try:
        start_dt = datetime.strptime(start_str, "%d.%m.%Y %H.%M")
        day_index = start_dt.weekday()
        time_index = get_time_slot_index(start_dt.time())
        if day_index > 4 or time_index is None:
            continue
        key = (code, teacher)
        preferences.setdefault(key, []).append((day_index, time_index))
    except:
        continue

preferences = {k: list(set(v)) for k, v in preferences.items()}

# Academic periods
EXTENDED_PERIODS = {
    "2022-P1": (datetime(2022, 9, 5), datetime(2022, 10, 30)),
    "2022-P2": (datetime(2022, 10, 31), datetime(2022, 12, 18)),
    "2023-P3": (datetime(2023, 1, 9), datetime(2023, 3, 19)),
    "2023-P4": (datetime(2023, 3, 20), datetime(2023, 5, 28)),
    "2023-P1": (datetime(2023, 9, 4), datetime(2023, 10, 29)),
    "2023-P2": (datetime(2023, 10, 30), datetime(2023, 12, 17)),
    "2024-P3": (datetime(2024, 1, 8), datetime(2024, 3, 17)),
    "2024-P4": (datetime(2024, 3, 18), datetime(2024, 5, 26)),
}

def assign_or_fallback_periods(start, end):
    valid = []
    for label, (p_start, p_end) in EXTENDED_PERIODS.items():
        if pd.notna(start) and pd.notna(end) and start >= p_start and end <= p_end:
            valid.append(label)
    if not valid:
        for label, (p_start, p_end) in EXTENDED_PERIODS.items():
            if pd.notna(start) and pd.notna(end) and (start <= p_end and end >= p_start):
                return [label]
    return valid if valid else []

df["ValidPeriods"] = df.apply(lambda row: assign_or_fallback_periods(row["Starts"], row["Ends"]), axis=1)

solver = Solver()
ROOMS = ["Agora 110AB", "Agora 115A", "Agora XX", "Quantum 111+112"]
WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_STRS = ["08:00–09:45", "10:00–11:45", "12:00–13:45", "14:00–15:45"]

course_vars = {}

for _, row in df.iterrows():
    code = row["Code"]
    teacher = row["Teacher"]
    for period in row["ValidPeriods"]:
        key = (code, period)
        d1 = Int(f"{code}_{period}_day1")
        t1 = Int(f"{code}_{period}_time1")
        r1 = Int(f"{code}_{period}_room1")

        if code != "IT00CD42":
            d2 = Int(f"{code}_{period}_day2")
            t2 = Int(f"{code}_{period}_time2")
            r2 = Int(f"{code}_{period}_room2")
        else:
            d2 = t2 = r2 = None

        course_vars[key] = {
            "day1": d1, "time1": t1, "room1": r1,
            "day2": d2, "time2": t2, "room2": r2
        }

        # Domain constraints
        solver.add(d1 >= 0, d1 <= 4, t1 >= 0, t1 <= 3, r1 >= 0, r1 < len(ROOMS))
        if d2 is not None:
            solver.add(d2 >= 0, d2 <= 4, t2 >= 0, t2 <= 3, r2 >= 0, r2 < len(ROOMS))
            solver.add(Or(d1 != d2, t1 != t2))
            solver.add(d1 != d2)

        # Special constraint for Project Course
        if code == "IT00CD42":
            solver.add(d1 == 4, t1 == 0, r1 == 0)

        # Teacher preference soft constraint
        pref_key = (code, teacher)
        prefs = preferences.get(pref_key, [])
        for label in [("day1", "time1"), ("day2", "time2")]:
            d_var = course_vars[key][label[0]]
            t_var = course_vars[key][label[1]]
            if d_var is not None and t_var is not None:
                soft = [And(d_var == d, t_var == t) for d, t in prefs]
                if soft:
                    solver.add(Or(*soft))

course_info = {
    (row["Code"], period): {"Teacher": row["Teacher"], "Group": row["Group"]}
    for _, row in df.iterrows()
    for period in row["ValidPeriods"]
}

keys = list(course_vars.keys())
for i in range(len(keys)):
    code1, p1 = keys[i]
    v1 = course_vars[keys[i]]
    info1 = course_info[keys[i]]

    for j in range(i + 1, len(keys)):
        code2, p2 = keys[j]
        if p1 != p2: continue
        v2 = course_vars[keys[j]]
        info2 = course_info[keys[j]]

        for a in [("day1", "time1", "room1"), ("day2", "time2", "room2")]:
            for b in [("day1", "time1", "room1"), ("day2", "time2", "room2")]:
                if v1[a[0]] is None or v2[b[0]] is None: continue
                same = And(v1[a[0]] == v2[b[0]], v1[a[1]] == v2[b[1]])
                solver.add(Implies(same, v1[a[2]] != v2[b[2]]))
                if info1["Teacher"] == info2["Teacher"]:
                    solver.add(Implies(same, v1[a[2]] != v2[b[2]]))
                if info1["Group"] == info2["Group"]:
                    solver.add(Implies(same, v1[a[2]] != v2[b[2]]))

if solver.check() == sat:
    model = solver.model()
    schedule = []

    for (code, period), vars in course_vars.items():
        row = df[df["Code"] == code].iloc[0]
        for label in [("day1", "time1", "room1"), ("day2", "time2", "room2")]:
            if vars[label[0]] is None: continue
            d = model[vars[label[0]]].as_long()
            t = model[vars[label[1]]].as_long()
            r = model[vars[label[2]]].as_long()
            time_str = "08:30–11:30" if code == "IT00CD42" else TIME_STRS[t]

            schedule.append({
                "Course Code": code,
                "Course Name": row["Nimi (en)"],
                "Teacher": row["Teacher"],
                "Period": period,
                "Day": WEEK_DAYS[d],
                "Time": time_str,
                "Room": ROOMS[r]
            })

    pd.DataFrame(schedule).to_excel("Final_Schedule_With_Course_Names_and_Teachers.xlsx", index=False)
    print("✅ Schedule saved as Excel file.")
else:
    print("❌ Solver could not find a valid solution.")

"""# Period wise visualization of schedule"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ✅ Load your generated schedule file
df = pd.read_excel("/content/Final_Schedule_With_Course_Names_and_Teachers.xlsx")
df.columns = df.columns.str.strip()

# Set consistent order for times and days
time_order = ["08:00–09:45", "10:00–11:45", "12:00–13:45", "14:00–15:45", "08:30–11:30"]
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

df["Time"] = df["Time"].astype(str)
df["Time"] = pd.Categorical(df["Time"], categories=time_order, ordered=True)

# Create folder for charts
os.makedirs("Period_Charts", exist_ok=True)

# Prepare Excel writer for single file
excel_writer = pd.ExcelWriter("All_Periods_Visual_Schedule.xlsx", engine='openpyxl')

# Loop through each period
for period in df["Period"].unique():
    period_df = df[df["Period"] == period]

    # 📊 Chart: Room Usage
    room_counts = period_df["Room"].value_counts().sort_values(ascending=False)
    plt.figure(figsize=(8, 4))
    sns.barplot(x=room_counts.index, y=room_counts.values)
    plt.title(f"{period}: Room Usage")
    plt.ylabel("Number of Classes")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"Period_Charts/{period}_Room_Usage.png")
    plt.close()

    # 📊 Chart: Classes per Day
    day_counts = period_df["Day"].value_counts().reindex(day_order)
    plt.figure(figsize=(8, 4))
    sns.barplot(x=day_counts.index, y=day_counts.values)
    plt.title(f"{period}: Classes per Day")
    plt.ylabel("Number of Classes")
    plt.tight_layout()
    plt.savefig(f"Period_Charts/{period}_Classes_Per_Day.png")
    plt.close()

    # 📄 Visual Weekly Table (Day × Time)
    pivot = period_df.pivot_table(
        index="Day",
        columns="Time",
        values="Course Name",
        aggfunc=lambda x: ', '.join(sorted(set(x)))
    )
    pivot = pivot.reindex(index=day_order, columns=time_order)

    # Write this period's table to its own Excel sheet
    pivot.to_excel(excel_writer, sheet_name=period)

# Save the combined Excel file
excel_writer.close()

print("✅ Visual schedules saved to All_Periods_Visual_Schedule.xlsx")
print("✅ Per-period charts saved to 'Period_Charts/' folder.")

import shutil

# Create ZIP from charts folder
shutil.make_archive("Period_Charts", 'zip', "Period_Charts")

# Provide download link
from google.colab import files
files.download("Period_Charts.zip")

# 📦 REQUIRED: Install if missing
!pip install pandas openpyxl

# 📊 CONVERT SMT SCHEDULE INTO CUSTOM EXCEL FORMAT BY YEAR

import pandas as pd

# 📄 Load your full schedule
df = pd.read_excel("/content/Final_Schedule_With_Course_Names_and_Teachers.xlsx")
df.columns = df.columns.str.strip()

# 📅 Step 1: Map periods to academic years
period_to_year = {
    "2022-P1": "2022-2023", "2022-P2": "2022-2023",
    "2023-P1": "2023-2024", "2023-P2": "2023-2024",
    "2023-P3": "2023-2024", "2023-P4": "2023-2024",
    "2024-P3": "2024-2025", "2024-P4": "2024-2025"
}
df["Academic Year"] = df["Period"].map(period_to_year)

# 🗓️ Step 2: Translate day names into Swedish
swedish_days = {
    "Monday": "Måndag",
    "Tuesday": "Tisdag",
    "Wednesday": "Onsdag",
    "Thursday": "Torsdag",
    "Friday": "Fredag"
}
df["Dag"] = df["Day"].map(swedish_days)

# ⏰ Step 3: Simplify time format (e.g., "08:00–09:45" → "08–10")
time_replace = {
    "08:00–09:45": "08–10",
    "10:00–11:45": "10–12",
    "12:00–13:45": "12–14",
    "14:00–15:45": "14–16",
    "08:30–11:30": "08–11"
}
df["Tid"] = df["Time"].map(time_replace).fillna(df["Time"])

# 🧾 Step 4: Prepare final columns
df_export = df[[
    "Academic Year", "Course Code", "Course Name", "Dag", "Tid", "Room"
]].rename(columns={
    "Course Code": "Kurskod",
    "Course Name": "Kursnamn",
    "Room": "Plats"
})

# 🧠 Step 5: Write to Excel with one sheet per year
writer = pd.ExcelWriter("Formatted_Schedule_By_Year.xlsx", engine="openpyxl")

for year in sorted(df_export["Academic Year"].dropna().unique()):
    year_df = df_export[df_export["Academic Year"] == year][[
        "Kurskod", "Kursnamn", "Dag", "Tid", "Plats"
    ]]
    year_df.to_excel(writer, index=False, sheet_name=year)

writer.close()

print("✅ Schedule formatted and saved as 'Formatted_Schedule_By_Year.xlsx'")