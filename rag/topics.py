"""Browse-by-topic categories.

Each topic groups one or more of Congress.gov's 32 policy areas (assigned to
every bill by the Congressional Research Service) under an everyday name.
Arts/culture, history and sports bills aren't shown under any topic.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    icon: str
    description: str
    policy_areas: tuple[str, ...]

TOPICS = [
    Topic("health", "Health", "🩺",
          "Health care, insurance, Medicare and Medicaid, prescription drugs and public health",
          ("Health",)),
    Topic("housing", "Housing", "🏠",
          "Housing costs, homelessness, mortgages and community development",
          ("Housing and Community Development",)),
    Topic("education", "Education", "🎓",
          "Schools, colleges, student loans and job training",
          ("Education",)),
    Topic("economy", "Economy & taxes", "💵",
          "Taxes, the federal budget, banking, trade and business",
          ("Taxation", "Economics and Public Finance", "Finance and Financial Sector",
           "Commerce", "Foreign Trade and International Finance")),
    Topic("jobs", "Jobs & workers", "🧰",
          "Wages, workplace rules, unions and retirement plans",
          ("Labor and Employment",)),
    Topic("immigration", "Immigration", "🛂",
          "Border security, visas, asylum and citizenship",
          ("Immigration",)),
    Topic("environment", "Environment & energy", "🌎",
          "Climate, pollution, energy, public lands, water and wildlife",
          ("Environmental Protection", "Energy", "Public Lands and Natural Resources",
           "Water Resources Development", "Animals")),
    Topic("defense", "Defense & veterans", "🎖️",
          "The military, national security and veterans' benefits",
          ("Armed Forces and National Security",)),
    Topic("justice", "Crime, justice & civil rights", "⚖️",
          "Policing, courts, guns, civil rights and civil liberties",
          ("Crime and Law Enforcement", "Law", "Civil Rights and Liberties, Minority Issues")),
    Topic("technology", "Technology & science", "💻",
          "Tech, AI, privacy, telecommunications and scientific research",
          ("Science, Technology, Communications",)),
    Topic("families", "Families & social programs", "👪",
          "Social Security, income assistance, child care and support for families",
          ("Social Welfare", "Families")),
    Topic("agriculture", "Agriculture & food", "🌾",
          "Farms, food safety and nutrition programs like SNAP",
          ("Agriculture and Food",)),
    Topic("transportation", "Transportation & infrastructure", "🚆",
          "Roads, transit, aviation, public works and disaster response",
          ("Transportation and Public Works", "Emergency Management")),
    Topic("foreign-affairs", "Foreign affairs", "🌐",
          "Diplomacy, foreign aid, sanctions and international relations",
          ("International Affairs",)),
    Topic("government", "Government & elections", "🏛️",
          "Elections, federal agencies, Congress and government ethics",
          ("Government Operations and Politics", "Congress")),
    Topic("tribal", "Native American affairs", "🗺️",
          "Tribal lands, sovereignty, and federal services for tribes",
          ("Native Americans",)),
]

TOPICS_BY_SLUG = {t.slug: t for t in TOPICS}
