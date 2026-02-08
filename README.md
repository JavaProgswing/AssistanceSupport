# Support Assistance Portal

An AI-powered customer support assistance portal that leverages Google Gemini for intelligent interactions, image analysis for refund claims, and automated policy enforcement.

## 🚀 Features

*   **AI-Powered Chat Interface:** Intelligent conversational agent using Google Gemini to handle customer inquiries.
*   **Automated Image Analysis:** Validates refund claims by analyzing uploaded images of damaged products using Gemini Vision.
*   **Policy Enforcement:** Automatically applies company-specific return policies to decision-making.
*   **Multi-Tenancy Support:** Manages multiple companies with distinct profiles and policies.
*   **Admin Dashboard:** Comprehensive dashboard for administrators to view claims, manage escalations, and oversee refund queues.
*   **Real-time Stats:** Tracks interaction metrics, AI resolution rates, and customer satisfaction scores.
*   **Supabase Integration:** Robust database management for transactions, companies, and claims.

## 🛠️ Tech Stack

*   **Backend:** Python (FastAPI), Uvicorn
*   **Frontend:** Flutter (Web)
*   **AI/LLM:** Google Gemini (Generative AI & Vision)
*   **Database:** Supabase (PostgreSQL)
*   **Deployment:** Vercel

## 📂 Project Structure

*   `app/`: Contains the FastAPI backend application.
    *   `main.py`: Entry point for the API and static file serving.
    *   `services.py`: Business logic, AI integration, and database interactions.
*   `assistance_web/`: Specific frontend assets and Flutter web build.
*   `database_schema.sql`: SQL schema for setting up the Supabase database.
*   `vercel.json`: Configuration for deployment on Vercel.

## ⚡ Setup & Installation

### Prerequisites

*   Python 3.9+
*   Supabase Account & Project
*   Google Gemini API Key

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/assistance-portal.git
    cd assistance-portal
    ```

2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration:**
    Create a `.env` file in the root directory and add the following:
    ```env
    GEMINI_API_KEY=your_gemini_api_key
    SUPABASE_URL=your_supabase_url
    SUPABASE_KEY=your_supabase_key
    ```

4.  **Database Setup:**
    Run the SQL commands from `database_schema.sql` in your Supabase SQL editor to set up the tables.

### Running Locally

1.  **Start the server:**
    ```bash
    uvicorn app.main:app --reload
    ```
2.  **Access the application:**
    Open your browser and navigate to `http://localhost:8000`.

## 📖 Usage

1.  **Company Registration:**
    *   Use the API or potential setup scripts to register a company.
    *   A unique tagline and admin credentials will be generated.
2.  **Customer Support:**
    *   Navigate to `/{company_tagline}` to access the customer support chat.
    *   Users can chat, upload images for claims, and get instant feedback.
3.  **Admin Panel:**
    *   Navigate to `/api/admin/login` (or the respective frontend route) to log in.
    *   View pending claims, approve/reject refunds, and manage escalations.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

[MIT License](LICENSE)
