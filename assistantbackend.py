"""
AI Receptionist Universal Backend
Now with appointment conflict detection and all features integrated

10/8 Update - Now handles scenarios outside business hours

10/11 Twilio Implementation, Ai Assistant will now send text message upon schedule confirmation
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import os
#from twilio.rest import Client
import sqlite3


app = Flask(__name__)


# ============================================
# DATABASE INITIALIZATION
# ============================================

def init_database():
    """Initialize SQLite database for appointments"""
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS appointments
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       business_id
                       TEXT
                       NOT
                       NULL,
                       customer_name
                       TEXT,
                       phone
                       TEXT,
                       email
                       TEXT,
                       start_time
                       TIMESTAMP
                       NOT
                       NULL,
                       end_time
                       TIMESTAMP
                       NOT
                       NULL,
                       service
                       TEXT,
                       notes
                       TEXT,
                       status
                       TEXT
                       DEFAULT
                       'confirmed',
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP,
                       updated_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS orders
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       business_id
                       TEXT
                       NOT
                       NULL,
                       customer_name
                       TEXT,
                       phone
                       TEXT,
                       order_items
                       TEXT,
                       total
                       REAL,
                       pickup_time
                       TEXT,
                       delivery_address
                       TEXT,
                       special_instructions
                       TEXT,
                       status
                       TEXT
                       DEFAULT
                       'pending',
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS messages
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       business_id
                       TEXT
                       NOT
                       NULL,
                       caller_name
                       TEXT,
                       phone
                       TEXT,
                       message
                       TEXT,
                       priority
                       TEXT
                       DEFAULT
                       'normal',
                       status
                       TEXT
                       DEFAULT
                       'new',
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    conn.commit()
    conn.close()


# Initialize database on startup
init_database()


# ============================================
# BUSINESS CONFIGURATION SYSTEM
# ============================================

class BusinessConfig:
    """Load and manage business-specific configurations"""

    def __init__(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = json.load(f)

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def get_feature_config(self, feature: str) -> Dict:
        """Get configuration for a specific feature"""
        features = self.config.get('features', {})
        return features.get(feature, {})

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return feature in self.config.get('enabled_features', [])


# ============================================
# AFTER-HOURS HANDLER
# ============================================

class AfterHoursHandler:
    """Detects and handles after-hours calls"""

    def __init__(self, config):
        self.config = config

    def is_after_hours(self) -> Tuple[bool, str]:
        """
        Check if current time is outside business hours
        Returns: (is_after_hours, message)
        """
        now = datetime.now()
        current_day = now.strftime('%A').lower()
        current_time = now.time()

        business_hours = self.config.get('business_hours', {})
        hours_today = business_hours.get(current_day)

        # Check if closed today
        if not hours_today or hours_today == 'closed':
            return (True, self._get_closed_message(current_day))

        # Parse hours
        try:
            open_time_str, close_time_str = hours_today.split('-')
            open_time = datetime.strptime(open_time_str.strip(), '%H:%M').time()
            close_time = datetime.strptime(close_time_str.strip(), '%H:%M').time()

            if current_time < open_time:
                return (True, self._get_before_open_message(open_time))
            elif current_time > close_time:
                return (True, self._get_after_close_message())
            else:
                return (False, "")

        except Exception as e:
            print(f"Error parsing business hours: {e}")
            return (False, "")

    def _get_closed_message(self, day: str) -> str:
        """Message when business is closed today"""
        next_open = self._get_next_open_day()
        business_name = self.config.get('business_name', 'us')
        return f"Thank you for calling {business_name}! We're closed on {day.title()}s. We'll be open {next_open}. I'm happy to take a message or schedule an appointment for when we're open. How can I help you?"

    def _get_before_open_message(self, open_time) -> str:
        """Message when calling before opening"""
        open_str = open_time.strftime('%I:%M %p').lstrip('0')
        business_name = self.config.get('business_name', 'us')
        return f"Thank you for calling {business_name}! Our office opens at {open_str}. I'm here to help right now though - I can schedule an appointment, answer questions, or take a message. What can I do for you?"

    def _get_after_close_message(self) -> str:
        """Message when calling after closing"""
        next_open = self._get_next_open_time()
        business_name = self.config.get('business_name', 'us')
        return f"Thank you for calling {business_name}! Our office is currently closed for the day. We'll be open {next_open}. I'm here to help - I can schedule an appointment, answer questions, or take a message. How can I assist you?"

    def _get_next_open_day(self) -> str:
        """Get next day business is open"""
        business_hours = self.config.get('business_hours', {})
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

        now = datetime.now()
        current_day_index = now.weekday()

        for i in range(1, 8):
            next_day_index = (current_day_index + i) % 7
            next_day = days[next_day_index]
            hours = business_hours.get(next_day)

            if hours and hours != 'closed':
                try:
                    open_time = hours.split('-')[0].strip()
                    open_hour = datetime.strptime(open_time, '%H:%M').time()
                    return f"{next_day.title()} at {open_hour.strftime('%I:%M %p').lstrip('0')}"
                except:
                    return f"{next_day.title()}"

        return "during our business hours"

    def _get_next_open_time(self) -> str:
        """Get next opening time"""
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).strftime('%A').lower()

        business_hours = self.config.get('business_hours', {})
        tomorrow_hours = business_hours.get(tomorrow)

        if tomorrow_hours and tomorrow_hours != 'closed':
            try:
                open_time = tomorrow_hours.split('-')[0].strip()
                open_hour = datetime.strptime(open_time, '%H:%M').time()
                return f"tomorrow at {open_hour.strftime('%I:%M %p').lstrip('0')}"
            except:
                return "tomorrow"

        return self._get_next_open_day()



# ============================================
# PLUGIN SYSTEM - Base Class
# ============================================

class Plugin:
    """Base class for all business feature plugins"""

    def __init__(self, config: BusinessConfig):
        self.config = config

    def can_handle(self, intent: str) -> bool:
        """Check if this plugin can handle the given intent"""
        raise NotImplementedError

    def process(self, data: Dict) -> Dict:
        """Process the request and return response"""
        raise NotImplementedError


# ============================================
# APPOINTMENT PLUGIN - With Conflict Detection
# ============================================

class AppointmentPlugin(Plugin):
    """Handles appointment scheduling with conflict detection"""

    def can_handle(self, intent: str) -> bool:
        return intent in ['schedule_appointment', 'book_appointment', 'make_reservation']

    def process(self, data: Dict) -> Dict:
        """Process appointment booking with conflict checking"""

        appointment_data = {
            'customer_name': data.get('customer_name'),
            'phone': data.get('phone'),
            'email': data.get('email', ''),
            'date': data.get('date'),
            'time': data.get('time'),
            'service': data.get('service'),
            'notes': data.get('notes', ''),
            'business_id': data.get('business_id')
        }

        # Parse date/time
        try:
            appointment_datetime = self._parse_datetime(
                appointment_data['date'],
                appointment_data['time']
            )
        except Exception as e:
            return {
                'success': False,
                'message': "I couldn't understand that date or time. Could you please repeat it? For example, 'November 5th at 2:30 PM'?"
            }

        # Get service duration
        service_duration = self._get_service_duration(appointment_data['service'])

        # Check business hours
        if not self._is_within_business_hours(appointment_datetime, appointment_data['business_id']):
            hours_text = self._get_business_hours_text()
            return {
                'success': False,
                'message': f"I'm sorry, we're not open at that time. Our hours are {hours_text}. Would you like to schedule during our open hours?"
            }

        # Check availability
        is_available, conflict_message = self._check_availability(
            appointment_datetime,
            service_duration,
            appointment_data['business_id']
        )

        if not is_available:
            # Find alternative times
            alternatives = self._find_alternative_times(
                appointment_datetime,
                service_duration,
                appointment_data['business_id']
            )

            if alternatives:
                alt_text = ', '.join([alt['formatted'] for alt in alternatives[:3]])
                message = f"{conflict_message} I have these times available: {alt_text}. Which works better for you?"
            else:
                message = f"{conflict_message} Let me take your information and we'll call you back to find a time that works."

            return {
                'success': False,
                'message': message,
                'alternatives': alternatives,
                'action': 'suggest_alternatives'
            }

        # Book appointment
        result = self._book_appointment(appointment_data, appointment_datetime, service_duration)

        if result['success']:
            # Send notification
            self._notify_business(appointment_data, appointment_datetime)

            formatted_time = self._format_datetime(appointment_datetime)
            return {
                'success': True,
                'message': f"Perfect! I've scheduled your {appointment_data['service']} for {formatted_time}. We'll see you then!",
                'appointment_id': result['appointment_id']
            }
        else:
            return {
                'success': False,
                'message': "I'm having trouble booking that appointment. Let me take your information and someone will call you back to confirm."
            }

    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """Parse date and time strings"""
        date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%B %d, %Y', '%b %d, %Y']
        time_formats = ['%H:%M', '%I:%M %p', '%I:%M%p', '%I %p', '%I%p']

        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str.strip(), fmt).date()
                break
            except ValueError:
                continue

        if not parsed_date:
            raise ValueError(f"Could not parse date: {date_str}")

        parsed_time = None
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_str.strip(), fmt).time()
                break
            except ValueError:
                continue

        if not parsed_time:
            raise ValueError(f"Could not parse time: {time_str}")

        return datetime.combine(parsed_date, parsed_time)

    def _get_service_duration(self, service: str) -> int:
        """Get service duration in minutes"""
        features = self.config.get_feature_config('appointments')
        appointment_types = features.get('appointment_types', [])

        for apt_type in appointment_types:
            if apt_type.get('name', '').lower() == service.lower():
                return apt_type.get('duration', 30)

        return 30  # Default

    def _check_availability(self, start_time: datetime, duration: int, business_id: str) -> tuple:
        """Check if time slot is available"""
        end_time = start_time + timedelta(minutes=duration)

        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()

        cursor.execute('''
                       SELECT customer_name, start_time, service
                       FROM appointments
                       WHERE business_id = ?
                         AND status = 'confirmed'
                         AND (
                           (start_time < ? AND end_time > ?)
                               OR (start_time < ? AND end_time > ?)
                               OR (start_time >= ? AND end_time <= ?)
                           )
                       ''', (
                           business_id,
                           end_time.isoformat(), start_time.isoformat(),
                           end_time.isoformat(), end_time.isoformat(),
                           start_time.isoformat(), end_time.isoformat()
                       ))

        conflict = cursor.fetchone()
        conn.close()

        if conflict:
            conflict_time = datetime.fromisoformat(conflict[1])
            return (False, f"I'm sorry, that time is already booked.")

        return (True, "")

    def _is_within_business_hours(self, appointment_datetime: datetime, business_id: str) -> bool:
        """Check if within business hours"""
        business_hours = self.config.get('business_hours', {})
        day_name = appointment_datetime.strftime('%A').lower()

        hours = business_hours.get(day_name)
        if not hours or hours == 'closed':
            return False

        try:
            open_time, close_time = hours.split('-')
            open_hour = datetime.strptime(open_time.strip(), '%H:%M').time()
            close_hour = datetime.strptime(close_time.strip(), '%H:%M').time()
            appointment_time = appointment_datetime.time()

            return open_hour <= appointment_time <= close_hour
        except:
            return True

    def _get_business_hours_text(self) -> str:
        """Get readable business hours"""
        business_hours = self.config.get('business_hours', {})
        # Simple version - enhance as needed
        return "Monday-Friday 9am-5pm, Saturday 9am-2pm"

    def _find_alternative_times(self, requested: datetime, duration: int, business_id: str) -> List[Dict]:
        """Find alternative available times"""
        alternatives = []
        check_date = requested.date()

        for day_offset in range(7):
            current_date = check_date + timedelta(days=day_offset)
            business_hours = self.config.get('business_hours', {})
            day_name = current_date.strftime('%A').lower()
            hours = business_hours.get(day_name)

            if not hours or hours == 'closed':
                continue

            try:
                open_time, close_time = hours.split('-')
                open_hour = datetime.strptime(open_time.strip(), '%H:%M').time()
                close_hour = datetime.strptime(close_time.strip(), '%H:%M').time()
            except:
                continue

            current_time = datetime.combine(current_date, open_hour)
            end_of_day = datetime.combine(current_date, close_hour)

            while current_time + timedelta(minutes=duration) <= end_of_day:
                is_available, _ = self._check_availability(current_time, duration, business_id)

                if is_available:
                    alternatives.append({
                        'datetime': current_time.isoformat(),
                        'formatted': self._format_datetime(current_time)
                    })

                    if len(alternatives) >= 5:
                        return alternatives

                current_time += timedelta(minutes=30)

        return alternatives

    def _book_appointment(self, data: Dict, start_time: datetime, duration: int) -> Dict:
        """Book the appointment"""
        end_time = start_time + timedelta(minutes=duration)

        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()

        cursor.execute('''
                       INSERT INTO appointments (business_id, customer_name, phone, email, start_time, end_time,
                                                 service, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (
                           data['business_id'], data['customer_name'], data['phone'], data['email'],
                           start_time.isoformat(), end_time.isoformat(), data['service'], data['notes']
                       ))

        appointment_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {'success': True, 'appointment_id': f"apt_{appointment_id}"}

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime for display"""
        return dt.strftime('%A, %B %d at %I:%M %p')

    def _notify_business(self, data: Dict, dt: datetime):
        """Send notification"""
        notification_config = self.config.get('notifications', {})
        formatted_time = self._format_datetime(dt)

        message = f"""New Appointment:
Customer: {data['customer_name']}
Phone: {data['phone']}
Service: {data['service']}
Time: {formatted_time}
Notes: {data.get('notes', 'None')}"""


        print(f"📧 Notification: {message}")
        # TODO: Implement email/SMS

# ============================================
# CANCELLATION PLUGIN
# ============================================

class CancellationPlugin(Plugin):
    def __init__(self, config):
        self.config = config
        self.db_path = os.path.join(os.getcwd(), "appointments.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def can_handle(self, intent: str) -> bool:
        return intent in ['cancellation', 'cancel']

    def process(self, data: Dict) -> Dict:
        """Delete an appointment from the database by name, phone, and start_time"""
        name = data.get("customer_name")
        phone = data.get("phone")
        start_time = data.get("start_time")

        if not all([name, phone]):
            return {
                "success": False,
                "message": "Missing details. Provide name and phone."
            }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if appointment exists
        print(f"🔍 Looking for: {name}, {phone}")

        cursor.execute("""
                       SELECT id
                       FROM appointments
                       WHERE customer_name = ?
                         AND phone = ?
                       """, (name, phone))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"success": False, "message": "No matching appointment found."}

        appointment_id = row[0]

        # Delete appointment
        cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        conn.commit()
        conn.close()

        print(f"🗑️ Deleted appointment for {name} at {start_time}")

        return {
            "success": True,
            "message": f"Your appointment at {start_time} has been canceled successfully."
        }


# ============================================
# ORDER PLUGIN
# ============================================

class OrderPlugin(Plugin):
    """Handles orders for restaurants/retail"""

    def can_handle(self, intent: str) -> bool:
        return intent in ['place_order', 'order_food', 'make_order']

    def process(self, data: Dict) -> Dict:
        order_data = {
            'customer_name': data.get('customer_name'),
            'phone': data.get('phone'),
            'order_items': data.get('order_items', ''),
            'total': data.get('total', 0),
            'pickup_time': data.get('pickup_time'),
            'delivery_address': data.get('delivery_address', ''),
            'special_instructions': data.get('special_instructions', ''),
            'business_id': data.get('business_id')
        }

        # Store order
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()

        cursor.execute('''
                       INSERT INTO orders (business_id, customer_name, phone, order_items, total,
                                           pickup_time, delivery_address, special_instructions)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (
                           order_data['business_id'], order_data['customer_name'],
                           order_data['phone'], order_data['order_items'], order_data['total'],
                           order_data['pickup_time'], order_data['delivery_address'],
                           order_data['special_instructions']
                       ))

        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Notify business
        self._notify_business(order_data)

        return {
            'success': True,
            'message': f"Great! Your order is confirmed for pickup at {order_data['pickup_time']}. Order number #{order_id}.",
            'order_id': f"order_{order_id}"
        }

    def _notify_business(self, data: Dict):
        message = f"""New Order:
Customer: {data['customer_name']} ({data['phone']})
Items: {data['order_items']}
Total: ${data['total']}
Pickup: {data['pickup_time']}
Notes: {data.get('special_instructions', 'None')}"""

        print(f"📧 Order Notification: {message}")
        # TODO: Implement email/SMS


# ============================================
# FAQ PLUGIN
# ============================================

class FAQPlugin(Plugin):
    """Handles frequently asked questions"""

    def can_handle(self, intent: str) -> bool:
        return intent in ['ask_question', 'faq', 'inquiry']

    def process(self, data: Dict) -> Dict:
        question = data.get('question', '').lower()
        faq_config = self.config.get_feature_config('faq')

        answer = self._find_answer(question, faq_config)

        if answer:
            return {'success': True, 'answer': answer}
        else:
            self._log_unknown_question(question, data.get('business_id'))
            return {
                'success': False,
                'answer': "I'm not sure about that. Let me take your information and someone will call you back."
            }

    def _find_answer(self, question: str, faq_config: Dict) -> Optional[str]:
        faqs = faq_config.get('questions', {})

        for keywords, answer in faqs.items():
            if any(keyword.strip() in question for keyword in keywords.split('|')):
                return answer

        return None

    def _log_unknown_question(self, question: str, business_id: str):
        print(f"❓ Unknown question for {business_id}: {question}")


# ============================================
# MESSAGE PLUGIN
# ============================================

class MessagePlugin(Plugin):
    """Takes messages"""

    def can_handle(self, intent: str) -> bool:
        return intent in ['leave_message', 'take_message', 'callback']

    def process(self, data: Dict) -> Dict:
        message_data = {
            'caller_name': data.get('caller_name'),
            'phone': data.get('phone'),
            'message': data.get('message'),
            'priority': data.get('priority', 'normal'),
            'business_id': data.get('business_id')
        }

        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()

        cursor.execute('''
                       INSERT INTO messages (business_id, caller_name, phone, message, priority)
                       VALUES (?, ?, ?, ?, ?)
                       ''', (
            message_data['business_id'], message_data['caller_name'],
            message_data['phone'], message_data['message'], message_data['priority']
                       ))

        message_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self._notify_business(message_data)

        return {
            'success': True,
            'message': "I've taken your message and someone will get back to you shortly."
        }

    def _notify_business(self, data: Dict):
        message = f"""New Message:
From: {data['caller_name']} ({data['phone']})
Message: {data['message']}
Priority: {data['priority']}"""

        print(f"📧 Message Notification: {message}")
        # TODO: Implement email/SMS


# ============================================
# PLUGIN MANAGER
# ============================================

class PluginManager:
    """Manages all plugins"""

    def __init__(self, config: BusinessConfig):
        self.config = config
        self.plugins = self._load_plugins()

    def _load_plugins(self) -> List[Plugin]:
        plugins = []
        enabled_features = self.config.get('enabled_features', [])

        if 'appointments' in enabled_features or 'reservations' in enabled_features:
            plugins.append(AppointmentPlugin(self.config))

        if 'orders' in enabled_features:
            plugins.append(OrderPlugin(self.config))

        if 'faq' in enabled_features:
            plugins.append(FAQPlugin(self.config))

        if 'messages' in enabled_features:
            plugins.append(MessagePlugin(self.config))

        if 'cancellations' in enabled_features:
            plugins.append(CancellationPlugin(self.config))

        return plugins

    def route_request(self, intent: str, data: Dict) -> Dict:
        for plugin in self.plugins:
            if plugin.can_handle(intent):
                return plugin.process(data)

        return {
            'success': False,
            'message': "I'm not sure how to help with that. Let me take your information."
        }


# ============================================
# FLASK API ENDPOINTS
# ============================================

@app.route('/webhook/vapi', methods=['POST'])
def vapi_webhook():
    """Main webhook for Vapi with after-hours detection"""
    try:
        data = request.json
        print(f"📞 Webhook received: {json.dumps(data, indent=2)}")

        # Extract business ID
        business_id = data.get('business_id') or data.get('metadata', {}).get('business_id')

        if not business_id:
            return jsonify({'success': False, 'error': 'No business_id provided'}), 400

        # Load config
        config_file = f'config/{business_id}.json'
        if not os.path.exists(config_file):
            return jsonify({'success': False, 'error': f'Config not found for {business_id}'}), 404

        config = BusinessConfig(config_file)

        # ⭐ CHECK IF AFTER HOURS
        after_hours_handler = AfterHoursHandler(config)
        is_after_hours, after_hours_message = after_hours_handler.is_after_hours()

        # Log after-hours status
        if is_after_hours:
            print(f"🌙 AFTER HOURS CALL - {after_hours_message[:50]}...")
        else:
            print(f"☀️ DURING BUSINESS HOURS")

        # Extract intent and data
        intent = data.get('intent')
        call_data = data.get('data', {})
        call_data['business_id'] = business_id
        call_data['is_after_hours'] = is_after_hours

        # Add after-hours context to response if needed
        if is_after_hours:
            call_data['after_hours_message'] = after_hours_message

        # Route to plugin
        plugin_manager = PluginManager(config)
        result = plugin_manager.route_request(intent, call_data)

        # Add after-hours context to result
        if is_after_hours:
            result['after_hours'] = True
            result['after_hours_note'] = after_hours_message

            # If this was an appointment, add note
            if intent in ['schedule_appointment', 'book_appointment'] and result.get('success'):
                result['message'] += " You'll receive a confirmation when our office opens."

        print(f"✅ Response: {json.dumps(result, indent=2)}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': 'connected'
    })


@app.route('/business/<business_id>/config', methods=['GET'])
def get_business_config(business_id: str):
    """Get business config"""
    try:
        config = BusinessConfig(f'config/{business_id}.json')
        return jsonify(config.config)
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/business/<business_id>/appointments', methods=['GET'])
def get_appointments(business_id: str):
    """Get all appointments for a business"""
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id, customer_name, phone, start_time, service, status
                   FROM appointments
                   WHERE business_id = ?
                   ORDER BY start_time DESC LIMIT 50
                   ''', (business_id,))

    appointments = []
    for row in cursor.fetchall():
        appointments.append({
            'id': row[0],
            'customer_name': row[1],
            'phone': row[2],
            'start_time': row[3],
            'service': row[4],
            'status': row[5]
        })

    conn.close()
    return jsonify(appointments)


@app.route('/business/<business_id>/orders', methods=['GET'])
def get_orders(business_id: str):
    """Get all orders for a business"""
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id, customer_name, phone, order_items, total, pickup_time, status
                   FROM orders
                   WHERE business_id = ?
                   ORDER BY created_at DESC LIMIT 50
                   ''', (business_id,))

    orders = []
    for row in cursor.fetchall():
        orders.append({
            'id': row[0],
            'customer_name': row[1],
            'phone': row[2],
            'order_items': row[3],
            'total': row[4],
            'pickup_time': row[5],
            'status': row[6]
        })

    conn.close()
    return jsonify(orders)

@app.route("/webhook/vapi/test", methods=["POST"])
def testconnection_webhook():
    data = request.get_json(force=True)
    print("Incoming Vapi payload:", data)
    return jsonify({"message": "Received"})



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
