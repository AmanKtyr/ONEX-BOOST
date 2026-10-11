document.addEventListener('DOMContentLoaded', function () {
    const professions = [
        "Accountant", "Actor", "Architect", "Artist", "Attorney", "Banker", "Barber", "Beautician", "Broker", "Carpenter", "Cashier", "Chef", "Chemist", "Clerk", "Coach", "Consultant", "Cook", "Counselor", "Dancer", "Dentist", "Designer", "Developer", "Doctor", "Driver", "Economist", "Editor", "Electrician", "Engineer", "Farmer", "Firefighter", "Fisherman", "Florist", "Gardener", "Hairdresser", "Housekeeper", "Illustrator", "Instructor", "Janitor", "Journalist", "Judge", "Laborer", "Lawyer", "Librarian", "Lifeguard", "Machinist", "Manager", "Mechanic", "Musician", "Nanny", "Nurse", "Optician", "Painter", "Pharmacist", "Photographer", "Physician", "Pilot", "Plumber", "Police Officer", "Politician", "Professor", "Programmer", "Psychologist", "Receptionist", "Sailor", "Salesperson", "Scientist", "Secretary", "Singer", "Soldier", "Student", "Surgeon", "Tailor", "Teacher", "Technician", "Therapist", "Translator", "Travel Agent", "Veterinarian", "Waiter", "Waitress", "Welder", "Writer"
    ];

    const professionInput = document.getElementById('id_profession');

    if (professionInput) {
        const datalist = document.createElement('datalist');
        datalist.id = 'professions-list';

        professions.forEach(profession => {
            const option = document.createElement('option');
            option.value = profession;
            datalist.appendChild(option);
        });

        document.body.appendChild(datalist);
        professionInput.setAttribute('list', 'professions-list');
    }
});